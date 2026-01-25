import sys
import os
import json
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

def retrieve_context(question, user_email):
    contexts = []
    
    # --- 1. VECTOR SEARCH ---
    print(f"   -> 🔍 Vector Search for: '{question}'")
    try:
        vector_db = get_vector_db()
        # DEBUG: Check if we find anything at all
        docs = vector_db.similarity_search(
            question, 
            k=4, 
            filter={"source": {"$exists": True}}, # Check generic existence first
            namespace=user_email
        )
        
        print(f"      Found {len(docs)} vector chunks.") # <--- DEBUG PRINT
        
        for i, doc in enumerate(docs):
            contexts.append(f"[Vector Context]: {doc.page_content}")
            
    except Exception as e:
        print(f"      ⚠️ Vector Error: {e}")

    # --- 2. GRAPH SEARCH ---
    print("   -> 🕸️ Graph Search...")
    try:
        graph_db = get_graph_db()
        
        # Refresh schema to make sure we see the latest data
        graph_db.refresh_schema()
        print(f"      Schema: {graph_db.get_schema[:100]}...") # <--- DEBUG PRINT

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", 
            temperature=0,
            google_api_key=os.environ["GEMINI_API_KEY"]
        )
        
        # SIMPLIFIED: usage without the custom prompt for now.
        # We rely on 'return_direct=True' to just get the data.
        chain = GraphCypherQAChain.from_llm(
            llm=llm, 
            graph=graph_db, 
            verbose=True,
            allow_dangerous_requests=True
        )
        
        # We wrap this in a try/catch specifically for the "Empty Response" issue
        try:
            graph_response = chain.invoke({"query": question})
            result = graph_response.get("result", "")
            if result:
                contexts.append(f"[Graph Context]: {result}")
        except Exception as inner_e:
            print(f"      ⚠️ Graph Chain Error: {inner_e}")

    except Exception as e:
        print(f"      ⚠️ Graph Setup Failed: {e}")

    return "\n\n".join(contexts)


# --- LAMBDA HANDLER ---
def lambda_handler(event, context):
    """
    The Entry Point for the Frontend
    """
    try:
        # 1. Parse Input
        body = json.loads(event.get('body', '{}'))
        question = body.get('question')
        user_email = body.get('user_email') # Sent from frontend
        
        if not question or not user_email:
            return {"statusCode": 400, "body": "Missing question or email"}

        print(f"Query: {question} (User: {user_email})")

        # 2. Retrieve Hybrid Context
        combined_context = retrieve_context(question, user_email)
        
        # 3. Generate Answer (The RAG "Generation" Step)
        # We will add this in the next step!
        # For now, let's just return the context to prove it works.
        
        return {
            "statusCode": 200, 
            "body": json.dumps({
                "context": combined_context,
                "answer": "Generation coming soon..." # Placeholder
            })
        }

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps(str(e))}

if __name__ == "__main__":
    test_event = {
        "body": json.dumps({
            "question": "What are the fun facts about cryptology?",
            "user_email": "minhduongqo@gmail.com"
        })
    }
    print(lambda_handler(test_event, None))