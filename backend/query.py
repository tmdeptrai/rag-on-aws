import os
import json
from typing import List, Optional, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from pinecone import Pinecone
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# --- INITIALIZE CLIENTS ---
try:
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
    neo4j_driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
except Exception as e:
    print(f"Init Error: {e}")

# --- PYDANTIC MODELS ---

class GraphEntity(BaseModel):
    """Represents a Node or Relationship in a standardized way"""
    label: str
    text: str = "Unknown"
    
    @classmethod
    def from_neo4j(cls, obj: Any) -> "GraphEntity":
        # Handle Relationships (Check for 'type' attribute)
        if hasattr(obj, 'type'): 
            return cls(label="RELATIONSHIP", text=f"-[{obj.type}]->")
        
        # Handle Nodes (Check for 'labels' attribute)
        elif hasattr(obj, 'labels'):
            # Determine best display text
            props = dict(obj)
            # Strategy: ID > Name > Text > Title > Truncated Content
            display_text = (
                props.get('id') or 
                props.get('name') or 
                props.get('title') or 
                props.get('text', '')[:30] + "..."
            )
            return cls(label=list(obj.labels)[0] if obj.labels else "Node", text=str(display_text))
            
        # Fallback for primitives (Strings/Ints)
        return cls(label="VALUE", text=str(obj))

class RetrievalResult(BaseModel):
    """Unified schema for both Vector and Graph results"""
    type: str = Field(..., pattern="^(vector|graph)$")
    content: str
    score: float
    source: str



# --- HELPER FUNCTIONS ---

def get_embedding(text):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    return response.embeddings[0].values

def vector_search(question, user_email) -> List[dict]:
    print(f"   -> VECTOR SEARCH: '{question}'")
    try:
        vector = get_embedding(question)
        results = index.query(
            namespace=user_email,
            vector=vector,
            top_k=4,
            include_metadata=True,
            filter={"source": {"$exists": True}}
        )
        
        cleaned_results = []
        for match in results['matches']:
            # Pydantic-style validation
            res = RetrievalResult(
                type="vector",
                content=match['metadata']['text'],
                score=match['score'],
                source=match['metadata'].get('source', 'Unknown')
            )
            cleaned_results.append(res.model_dump())
            
        print(f"      ==> Vectors Found: {len(cleaned_results)} chunks")
        return cleaned_results
    except Exception as e:
        print(f"      VECTOR ERROR: {e}")
        return []

def graph_search(question) -> List[dict]:
    print("   -> GRAPH SEARCH...")
    try:
        prompt = f"""
            Task: Write a Cypher query to find the main entity in this question and its connections.
            User Question: "{question}"
            
            Steps:
            1. Extract the core entity (e.g. "Who is Thomas Jefferson?" -> "Thomas Jefferson").
            2. Match that entity loosely.
            
            CRITICAL FORMATTING RULES:
            1. Use `MATCH (n)-[r]-(m)` to find connections.
            2. WHERE clause: `toLower(n.id) CONTAINS toLower('ENTITY_NAME')`
            3. RETURN full objects: `RETURN n, r, m LIMIT 15`
            4. Return ONLY raw Cypher.
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=prompt
        )
        cypher = response.text.strip().replace("```cypher", "").replace("```", "")
        print(f"      Generated Cypher: {cypher}")

        structured_results = []
        with neo4j_driver.session() as session:
            result = session.run(cypher)
            
            for record in result:
                # --- ROBUST PARSING WITH PYDANTIC LOGIC ---
                try:
                    triple_parts = []
                    for item in record.values():
                        # Parse every item using our Pydantic logic
                        entity = GraphEntity.from_neo4j(item)
                        triple_parts.append(entity.text)
                    
                    # Join: "Thomas Jefferson" + "-[INVENTED]->" + "Cipher Wheel"
                    fact_str = " ".join(triple_parts)
                    
                    res = RetrievalResult(
                        type="graph",
                        content=fact_str,
                        score=1.0,
                        source="Knowledge Graph"
                    )
                    structured_results.append(res.model_dump())
                except Exception as parse_err:
                    print(f"      ⚠️ Record Parse Error: {parse_err}")
                    continue
        
        print(f"      ==> Graph Found: {len(structured_results)} facts")
        return structured_results
    except Exception as e:
        print(f"      ⚠️ Graph Error: {e}")
        return []

# --- LAMBDA HANDLER ---

def lambda_handler(event, context):
    try:
        # 1. Parse Input
        if isinstance(event.get('body'), str):
            body = json.loads(event.get('body', '{}'))
        else:
            body = event.get('body', {})
            
        question = body.get('question')
        user_email = body.get('user_email')
        
        if not question or not user_email:
            return {"statusCode": 400, "body": "Missing inputs"}

        # 2. Retrieve & Combine
        vector_data = vector_search(question, user_email)
        graph_data = graph_search(question)
        
        all_sources = vector_data + graph_data
        
        # 3. Flatten for LLM
        context_text_list = [item['content'] for item in all_sources]
        combined_context_str = "\n".join(context_text_list)
        
        if not combined_context_str:
            combined_context_str = "No specific data found."

        # 4. Generate Answer
        system_instruction = f"""
            You are a helpful assistant. Answer based ONLY on the context below.
            
            Context:
            {combined_context_str}
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0
            )
        )

        return {
            "statusCode": 200, 
            "body": json.dumps({
                "answer": response.text,
                "references": all_sources
            })
        }

    except Exception as e:
        print(f"CRITICAL: {e}")
        return {"statusCode": 500, "body": json.dumps(str(e))}

# --- LOCAL TEST ---
if __name__ == "__main__":
    test_event = {
        "body": {
            "question": "Who is Thomas Jefferson?", 
            "user_email": "minhduongqo@gmail.com",
        }
    }
    resp = lambda_handler(test_event, None)
    
    if resp['statusCode'] == 200:
        data = json.loads(resp['body'])
        print(f"\n==> Answer: {data['answer']}\n")
        print(f"? References ({len(data['references'])}):")
        for ref in data['references']:
            if ref['type'] == 'graph':
                print(f"   Graph: {ref['content']}")
            else:
                print(f"   Vector:{ref['content'][:100]}")    