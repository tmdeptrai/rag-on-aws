import os
import sys
import json
import re
import boto3
import pymupdf
from typing import List, Dict, Any
from dotenv import load_dotenv
from urllib.parse import unquote_plus

# Clients
from google import genai
from google.genai import types
from pinecone import Pinecone
from neo4j import GraphDatabase

load_dotenv()

s3_client = boto3.client('s3')

try:
    genai_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    pc_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
    neo4j_driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
    )
except Exception as e:
    print(f"⚠️ Init Warning: {e}")

# --- HELPERS ---

def clean_scanned_text(text: str) -> str:
    """Regex to fix broken PDF text."""
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def recursive_split(text: str, chunk_size=1000, overlap=100) -> List[str]:
    """Simple recursive chunker."""
    if len(text) <= chunk_size: return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            split_point = text.rfind('. ', start, end)
            if split_point == -1: split_point = text.rfind(' ', start, end)
            if split_point != -1 and split_point > start: end = split_point + 1
        chunk = text[start:end].strip()
        if chunk: chunks.append(chunk)
        start = end - overlap
    return chunks

# --- INGESTION LOGIC ---

def ingest_vectors(chunks: List[str], metadata: Dict, namespace: str):
    print(f"   -> Embedding {len(chunks)} chunks...")
    vectors_to_upsert = []
    
    for i, text in enumerate(chunks):
        try:
            resp = genai_client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
            )
            embedding = resp.embeddings[0].values
            
            # ID format: "filename_chunkIndex"
            chunk_id = f"{metadata['source_file']}_{i}"
            
            vectors_to_upsert.append({
                "id": chunk_id,
                "values": embedding,
                "metadata": {
                    "text": text,
                    "source": metadata['source_file'],
                    "user_email": metadata['user_email']
                }
            })
        except Exception as e:
            print(f"      Chunk {i} embedding failed: {e}")

    if vectors_to_upsert:
        pc_index.upsert(vectors=vectors_to_upsert, namespace=namespace)
        print(f"      Upserted {len(vectors_to_upsert)} vectors.")

def ingest_graph_global(full_text: str, metadata: Dict):
    """
    Extracts graph from the WHOLE text at once.
    Pros: Better context understanding (Co-reference resolution).
    Cons: Limited by token window (approx 30k words for cheap models).
    """
    print("   -> Extracting Global Graph Data...")
    
    # 1. Safety Check: If text is too huge, truncate or warn
    # (Gemini Flash has a huge window, so this is usually fine for <100 pages)
    if len(full_text) > 100000:
        print("      ⚠️ Text > 100k chars. Truncating for graph extraction safety.")
        graph_text = full_text[:100000]
    else:
        graph_text = full_text

    graph_schema = {
        "type": "OBJECT",
        "properties": {
            "triples": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "head": {"type": "STRING"},
                        "tail": {"type": "STRING"},
                        "relationship": {"type": "STRING"}
                    },
                    "required": ["head", "tail", "relationship"]
                }
            }
        },
        "required": ["triples"]
    }

    try:
        # 2. Single LLM Call
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Extract all knowledge triples. Focus on entities and how they connect. Text: {graph_text}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=graph_schema,
                temperature=0
            )
        )
        
        data = json.loads(response.text)
        triples = data.get("triples", [])
        
        if not triples:
            print("      ⚠️ No triples found.")
            return

        # 3. Clean Relationships
        for t in triples:
            t['relationship'] = t['relationship'].upper().replace(" ", "_")

        # 4. Batch Ingest
        cypher_query = """
            UNWIND $triples AS t
            MERGE (h:Entity {id: t.head}) 
            ON CREATE SET h.user_email = $email, h.source = $source
            
            MERGE (tail:Entity {id: t.tail})
            ON CREATE SET tail.user_email = $email, tail.source = $source
            
            MERGE (h)-[r:RELATED_TO {original_type: toUpper(t.relationship)}]->(tail)
        """
        
        with neo4j_driver.session() as session:
            session.run(
                cypher_query, 
                triples=triples, 
                email=metadata['user_email'], 
                source=metadata['source_file']
            )
            
        print(f"      Global Graph extraction complete. {len(triples)} edges created.")
        
    except Exception as e:
        print(f"      Graph extraction failed: {e}")

def update_status(bucket, key, status):
    try:
        s3_client.put_object_tagging(
            Bucket=bucket, Key=key,
            Tagging={'TagSet': [{'Key': 'status', 'Value': status}]}
        )
    except Exception as e:
        print(f"Tag Update Failed: {e}")

# --- MAIN HANDLER ---

def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        raw_key = record['s3']['object']['key']
        key = unquote_plus(raw_key)

        print(f"Processing: {key}")
        update_status(bucket, key, "indexing")
        
        try:
            # A. Download
            obj = s3_client.get_object(Bucket=bucket, Key=key)
            pdf_bytes = obj['Body'].read()
            
            # B. Extract & Clean
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            raw_text = ""
            for page in doc:
                raw_text += page.get_text("text", flags=4)
            
            text = clean_scanned_text(raw_text)
            if not text:
                print("Skipping empty file.")
                continue

            # Metadata
            try: user_email = key.split('/')[1]
            except: user_email = "default_user"
            metadata = {"user_email": user_email, "source_file": key}

            # --- NEW PIPELINE ORDER ---
            
            # C. GRAPH FIRST (Global Context)
            ingest_graph_global(text, metadata)

            # D. CHUNK & VECTOR SECOND
            chunks = recursive_split(text)
            print(f"   -> Split into {len(chunks)} chunks for Vectors.")
            ingest_vectors(chunks, metadata, namespace=user_email)
            
            update_status(bucket, key, "ready")
            print(f"Finished {key}")

        except Exception as e:
            print(f"Failed {key}: {e}")
            update_status(bucket, key, "failed")

    return {"status": "processed"}

if __name__ == "__main__":
    # Local Test
    test_event = {
        "Records": [{
            "s3": {
                "bucket": {"name": os.getenv("S3_BUCKET_NAME")},
                "object": {"key": "documents/minhduongqo@gmail.com/bfbb0dac_FUN-FACTS-SHEET.pdf"} 
            }
        }]
    }
    lambda_handler(test_event, None)