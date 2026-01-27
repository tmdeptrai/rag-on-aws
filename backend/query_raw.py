import os
import json
from google import genai
from google.genai import types
from pinecone import Pinecone
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# --- 1. INITIALIZE CLIENTS ---
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

# --- 2. HELPER FUNCTIONS ---

def get_embedding(text):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    return response.embeddings[0].values

def vector_search(question, user_email):
    print(f"   -> 🔍 Vector Search: '{question}'")
    try:
        vector = get_embedding(question)
        results = index.query(
            namespace=user_email,
            vector=vector,
            top_k=4,
            include_metadata=True,
            filter={"source": {"$exists": True}}
        )
        
        # CHANGED: Return structured objects instead of just text
        structured_results = []
        for match in results['matches']:
            structured_results.append({
                "type": "vector",
                "content": match['metadata']['text'],
                "score": match['score'], # Pinecone similarity score (0.0 to 1.0)
                "source": match['metadata'].get('source', 'Unknown')
            })
        return structured_results
    except Exception as e:
        print(f"      ⚠️ Vector Error: {e}")
        return []

def graph_search(question):
    print("   -> 🕸️ Graph Search...")
    try:
        prompt = f"""
        Task: Write a Cypher query for this question.
        Schema: (Person, Organization, Concept, Event) connected by [INVENTED, LOCATED_IN, RELATED_TO, PARTICIPATED_IN].
        Question: "{question}"
        Instructions: Return ONLY the raw Cypher code. No markdown.
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
                # Format: "Thomas Jefferson -> INVENTED -> Cipher Wheel"
                fact_str = " -> ".join([str(v) for v in record.values()])
                
                # CHANGED: Return structured object
                structured_results.append({
                    "type": "graph",
                    "content": fact_str,
                    "score": 1.0, # Graphs represent 'facts', so we give max confidence
                    "source": "Knowledge Graph"
                })
        return structured_results
    except Exception as e:
        print(f"      ⚠️ Graph Error: {e}")
        return []

# --- 3. LAMBDA HANDLER ---

def lambda_handler(event, context):
    try:
        # 1. Parse Input
        if isinstance(event.get('body'), str):
            body = json.loads(event.get('body', '{}'))
        else:
            body = event.get('body', {})
            
        question = body.get('question')
        user_email = body.get('user_email')
        history = body.get('history', []) 
        
        if not question or not user_email:
            return {"statusCode": 400, "body": "Missing inputs"}

        # 2. Retrieve Structured Context
        vector_data = vector_search(question, user_email)
        graph_data = graph_search(question)
        
        # Combine all sources for the Response JSON
        all_sources = vector_data + graph_data
        
        # Flatten plain text for the LLM System Prompt
        context_text_list = [item['content'] for item in all_sources]
        combined_context_str = "\n".join(context_text_list)
        
        # 3. Construct System Prompt
        system_instruction = f"""
        You are a helpful assistant. Answer based ONLY on the context below.
        
        Context:
        {combined_context_str}
        """

        # 4. Generate Answer
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=history + [{"role": "user", "parts": [{"text": question}]}],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0
            )
        )

        return {
            "statusCode": 200, 
            "body": json.dumps({
                "answer": response.text,
                "references": all_sources # <--- Now returning full details + scores
            })
        }

    except Exception as e:
        print(f"CRITICAL: {e}")
        return {"statusCode": 500, "body": json.dumps(str(e))}

# --- LOCAL TEST ---
if __name__ == "__main__":
    test_event = {
        "body": {
            "question": "Where is it located?", 
            "user_email": "minhduongqo@gmail.com",
            "history": [
                {"role": "user", "parts": [{"text": "Who is Thomas Jefferson?"}]},
            ]
        }
    }
    resp = lambda_handler(test_event, None)
    
    # Pretty Print Result
    if resp['statusCode'] == 200:
        data = json.loads(resp['body'])
        print(f"\n🤖 Answer: {data['answer']}\n")
        print("📚 References:")
        for ref in data['references']:
            print(f"   [{ref['type'].upper()} | Score: {ref['score']:.2f}] {ref['content'][:100]}...")
    else:
        print(resp)