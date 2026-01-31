import os, tempfile
import json
import re
import boto3
import pymupdf
from typing import List, Dict
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
    print(f"Init Warning: {e}")

# --- HELPERS ---

def clean_scanned_text(text: str) -> str:
    """Regex to fix broken PDF text."""
    text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def recursive_split(text: str, chunk_size=1000, overlap=100) -> List[str]:
    if len(text) <= chunk_size: return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        
        # Smart Split: Try to break at a period or space
        if end < len(text):
            split_point = text.rfind('. ', start, end)
            if split_point == -1: 
                split_point = text.rfind(' ', start, end)
            
            # Only use split_point if it's reasonable (not causing backward/stagnant loop)
            # We ensure 'end' is at least 'start + overlap + 1' to force progress
            if split_point != -1 and split_point > (start + overlap): 
                end = split_point + 1
        
        chunk = text[start:end].strip()
        if chunk: chunks.append(chunk)
        
        # Ensure we always advance by at least 1 character
        # If (end - overlap) is <= start, just force start += 1 to break the loop
        next_start = end - overlap
        if next_start <= start:
            start += max(1, chunk_size - overlap) # Force jump forward
        else:
            start = next_start
            
    return chunks

# --- INGESTION LOGIC ---

def ingest_vectors(chunks: List[str], metadata: Dict, namespace: str):
    BATCH_SIZE = 50 # Process 50 chunks at a time
    print(f"   -> Embedding {len(chunks)} chunks (Batch Mode)...")
    
    total_upserted = 0
    
    # Process in batches
    for i in range(0, len(chunks), BATCH_SIZE):
        batch_chunks = chunks[i : i + BATCH_SIZE]
        vectors_to_upsert = []
        
        # 1. Embed Batch
        for j, text in enumerate(batch_chunks):
            try:
                # Add strict timeout/retry logic here if needed
                resp = genai_client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=text,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                embedding = resp.embeddings[0].values
                
                # Global Index ID
                global_idx = i + j
                chunk_id = f"{metadata['source_file']}_{global_idx}"
                
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
                print(f"      Chunk {i+j} failed: {e}")

        # 2. Upsert Batch Immediately
        if vectors_to_upsert:
            try:
                pc_index.upsert(vectors=vectors_to_upsert, namespace=namespace)
                total_upserted += len(vectors_to_upsert)
            except Exception as e:
                print(f"      Pinecone Batch Error: {e}")
                
        # 3. Memory Cleanup (Crucial for Python)
        del vectors_to_upsert 
        
    print(f"      Upserted {total_upserted} vectors total.")


def ingest_graph_summary(full_text: str, metadata: Dict):
    """
    Summarizes the doc first, then extracts graph.
    """
    print("   -> Extracting Graph from Summary (Fast Mode)...")
    
    # 1. Prepare Text (Gemini Flash has 1M token window, so we can usually send it all)
    # But let's limit to 30k chars to be safe/fast for the summary.
    if len(full_text) > 50000:
        # Take Start + Middle + End to get good coverage
        input_text = full_text[:20000] + "\n...\n" + full_text[-20000:]
    else:
        input_text = full_text
        
    try:
        # --- STEP A: GENERATE DENSE SUMMARY ---
        summary_prompt = f"""
            Analyze the following text and generate a detailed summary. 
            Focus specifically on identifying the key entities (people, organizations, dates, concepts) 
            and exactly how they are related. 
            Text: {input_text}
        """
        
        summary_resp = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=summary_prompt
        )
        summary_text = summary_resp.text

        # --- STEP B: EXTRACT GRAPH FROM SUMMARY ---
        # Now we extract from the summary, which is dense and short.
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

        response = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Extract knowledge triples from this summary. Use active, precise verbs (e.g., 'INVENTED', 'LOCATED_IN'). Summary: {summary_text}",
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=graph_schema,
                temperature=0
            )
        )
        
        data = json.loads(response.text)
        triples = data.get("triples", [])
        
        if not triples:
            print("      No triples found in summary.")
            return

        # --- STEP C: SAVE TO NEO4J ---
        # Group by relationship for batching
        triples_by_type = {}
        for t in triples:
            raw_rel = t['relationship'].upper().replace(" ", "_")
            rel_type = "".join(c for c in raw_rel if c.isalnum() or c == "_")
            if not rel_type: continue
            
            if rel_type not in triples_by_type: triples_by_type[rel_type] = []
            triples_by_type[rel_type].append(t)

        with neo4j_driver.session() as session:
            for rel_type, items in triples_by_type.items():
                cypher = f"""
                    UNWIND $triples AS t
                    MERGE (h:Entity {{id: t.head, user_email: $email}}) 
                    ON CREATE SET h.source = $source
                    
                    MERGE (tail:Entity {{id: t.tail, user_email: $email}}) 
                    ON CREATE SET tail.source = $source
                    
                    MERGE (h)-[r:{rel_type}]->(tail)
                """
                session.run(cypher, triples=items, email=metadata['user_email'], source=metadata['source_file'])
            
        print(f"      Graph summary complete. {len(triples)} edges created.")
        
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
        
        tmp_path = None
        
        try:
            # A. Download
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                s3_client.download_fileobj(bucket, key, tmp_file)
                tmp_path = tmp_file.name
            
            # B. Extract & Clean
            # 2. LAZY LOAD (Reads pages on-demand)
            doc = pymupdf.open(tmp_path) 
            text_pages = [] 
            
            for page in doc:
                text_pages.append(page.get_text("text", flags=4))

            doc.close()
            
            # 4. ONE-TIME ALLOCATION
            raw_text = "".join(text_pages)
            del text_pages # Explicit garbage collection hint
            
            text = clean_scanned_text(raw_text)
            if not text:
                print("Skipping empty file.")
                continue

            # Metadata
            try: user_email = key.split('/')[1]
            except: user_email = "default_user"
            metadata = {"user_email": user_email, "source_file": key}

            
            # C. CHUNKING (Still needed for vectors)
            chunks = recursive_split(text)
            print(f"   -> Split into {len(chunks)} chunks.")

            # D. INGEST 
            # 1. Vectors (Detailed Search) - Uses chunks
            ingest_vectors(chunks, metadata, namespace=user_email)
            
            # 2. Graph (Global Context) - Uses Summary Strategy
            ingest_graph_summary(text, metadata) 
            
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
                "object": {"key": "documents/kimoanh16092005@gmail.com/e91f971c_data_analyst_learning_roadmap.pdf"} 
            }
        }]
    }
    lambda_handler(test_event, None)