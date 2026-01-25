import sys
import os
import json
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional

from langchain_neo4j import GraphCypherQAChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.db_connect import get_vector_db, get_graph_db
from dotenv import load_dotenv
load_dotenv()

# --- 2. DEFINE THE EXPECTED SCHEMA ---
class GraphTriple(BaseModel):
    """
    Represents a single fact retrieved from the Graph DB.
    Enforces the structure: Subject -> Predicate -> Object
    """
    subject: str
    predicate: str
    object: str

    def to_str(self):
        return f"{self.subject} -> {self.predicate} -> {self.object}"

def retrieve_context(question, user_email):
    contexts = []
    
    # --- A. VECTOR SEARCH ---
    print(f"   -> 🔍 Vector Search: '{question}'")
    try:
        vector_db = get_vector_db()
        docs = vector_db.similarity_search(
            question, 
            k=4, 
            filter={"source": {"$exists": True}}, 
            namespace=user_email
        )
        print(f"      Found {len(docs)} chunks.")
        for i, doc in enumerate(docs):
            contexts.append(f"[Vector Context]: {doc.page_content}")
    except Exception as e:
        print(f"      ⚠️ Vector Error: {e}")

    # --- B. GRAPH SEARCH (With Pydantic Validation) ---
    print("   -> 🕸️ Graph Search...")
    try:
        graph_db = get_graph_db()
        # graph_db.refresh_schema() # Uncomment if schema changes often

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", 
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY")
        )

        # 3. UPDATE PROMPT TO FORCE ALIASES (subject, predicate, object)
        cypher_generation_template = """
            Task: Generate a Cypher statement to query a graph database.
            Instructions:
            - Use only the provided relationship types and properties.
            - Do not generate explanations.
            - CRITICAL: You must alias your return values exactly as follows:
            RETURN node1.id AS subject, type(relationship) AS predicate, node2.id AS object

            Schema:
            {schema}

            Question: {question}

            Cypher Query:
        """
        
        cypher_prompt = PromptTemplate(
            template=cypher_generation_template, 
            input_variables=["schema", "question"]
        )

        chain = GraphCypherQAChain.from_llm(
            llm=llm, 
            graph=graph_db, 
            verbose=True,
            return_direct=True, 
            cypher_prompt=cypher_prompt,
            allow_dangerous_requests=True
        )
        
        try:
            graph_response = chain.invoke({"query": question})
            raw_result = graph_response.get("result", [])
            
            # 4. PYDANTIC VALIDATION LOOP
            facts = []
            if raw_result:
                for item in raw_result:
                    try:
                        # This line does the magic validation
                        triple = GraphTriple(**item)
                        facts.append(triple.to_str())
                    except ValidationError as ve:
                        print(f"      ⚠️ Malformed graph data: {item} - {ve}")
                        continue
                
                fact_string = " | ".join(facts)
                if fact_string:
                    contexts.append(f"[Graph Context]: {fact_string}")
                    print(f"      ✅ Valid Facts: {fact_string}")

        except Exception as inner_e:
            print(f"      ⚠️ Graph Execution Error: {inner_e}")

    except Exception as e:
        print(f"      ⚠️ Graph Setup Failed: {e}")
        
    return "\n\n".join(contexts)

# --- LAMBDA HANDLER ---
def lambda_handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        question = body.get('question')
        user_email = body.get('user_email')
        
        if not question or not user_email:
            return {"statusCode": 400, "body": "Missing inputs"}

        print(f"Query: {question} ({user_email})")
        combined_context = retrieve_context(question, user_email)
        
        return {
            "statusCode": 200, 
            "body": json.dumps({
                "context": combined_context,
                "answer": "Generation coming soon..." 
            })
        }
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps(str(e))}

if __name__ == "__main__":
    test_event = {
        "body": json.dumps({
            "question": "Where is Thomas Jefferson displayed in?",
            "user_email": "minhduongqo@gmail.com"
        })
    }
    print(lambda_handler(test_event, None))