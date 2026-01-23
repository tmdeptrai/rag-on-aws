import sys,os 
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)
from shared.db_connect import get_graph_db, get_vector_db

import json
import boto3
import io
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_experimental.graph_transformers import LLMGraphTransformer
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
load_dotenv()


s3_client = boto3.client('s3')

def update_status(bucket, key, status):
    """Updates the S3 object tag"""
    try:
        s3_client.put_object_tagging(
            Bucket=bucket,
            Key=key,
            Tagging={
                'TagSet': [{'Key': 'status', 'Value': status}]
            }
        )
    except Exception as e:
        print(f"Failed to update status tag: {e}")

def lambda_handler(event, context):
    """
    Triggered by S3 Object Created Event.
    Processes PDF -> Vector DB + Graph DB.
    """
    vector_db = get_vector_db()
    graph_db = get_graph_db()
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash", 
        temperature=0,
        google_api_key=os.environ["GEMINI_API_KEY"]
    )
    llm_transformer = LLMGraphTransformer(llm=llm)

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        print(f"Starting {key}...")
        update_status(bucket, key, "indexing")
        
        try:
            # A. Download PDF from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            file_content = response['Body'].read()
            
            # B. Extract Text (Simple PyPDF)
            pdf_file = io.BytesIO(file_content)
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            
            if not text.strip():
                print(f"⚠️ Warning: No text found in {key}. Skipping.")
                continue

            # C. Chunking
            try:
                user_email = key.split('/')[1]
            except IndexError:
                user_email = "default_user"

            doc = Document(page_content=text, metadata={"source": key, "user_email": user_email})
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            chunks = splitter.split_documents([doc])
            
            print(f"🧩 Split into {len(chunks)} chunks.")

            # D. Ingest into Upstash (Vector)
            print("   -> 💾 Ingesting into Vector DB...")
            vector_db.add_documents(chunks, namespace=user_email)
            
            # E. Ingest into Neo4j (Graph)
            print("   -> 🕸️ Extracting Graph Structure (This might take a moment)...")
            graph_docs = llm_transformer.convert_to_graph_documents(chunks)
            graph_db.add_graph_documents(
                graph_docs, 
                baseEntityLabel=True, 
                include_source=True
            )
            
            update_status(bucket, key, "ready")
            print(f"Finished {key}")

        except Exception as e:
            update_status(bucket, key, "failed")
            print(f"❌ Error: {e}")
            raise e

    return {"status": "success", "files_processed": len(event['Records'])}

# --- LOCAL TEST RUNNER ---
# This allows you to run "python backend/handlers/ingest.py" to test it!
if __name__ == "__main__":
    print("🧪 Running in Local Test Mode")
    
    # 1. Create a dummy S3 event looking exactly like AWS would send it
    test_event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": os.environ.get("S3_BUCKET_NAME")},
                    # Make sure this file actually exists in your S3 for the test!
                    "object": {"key": "documents/test_user/test_document.pdf"} 
                }
            }
        ]
    }
    
    # 2. Run the handler
    lambda_handler(test_event, None)  