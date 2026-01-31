import boto3
from botocore.config import Config
import uuid
import streamlit as st
import os, sys, time
from pinecone import Pinecone
from neo4j import GraphDatabase
from dotenv import load_dotenv
load_dotenv()

def load_secrets_to_env():
    for key, value in st.secrets.items():
        if key not in os.environ:
            os.environ[key] = str(value)
load_secrets_to_env()

if 's3_client' not in st.session_state:
    st.session_state.s3_client = boto3.client(
        's3',
        region_name = st.secrets["AWS_REGION"],
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        config=Config(signature_version='s3v4')
    )
    
BUCKET_NAME = st.secrets["S3_BUCKET_NAME"]    

@st.cache_resource
def init_db_connections():
    """
    Initializes and caches the bare-metal database clients.
    """
    # 1. Pinecone
    pc = Pinecone(api_key=st.secrets["PINECONE_API_KEY"])
    pc_index = pc.Index(st.secrets["PINECONE_INDEX_NAME"])
    
    # 2. Neo4j
    neo4j_driver = GraphDatabase.driver(
        st.secrets["NEO4J_URI"],
        auth=(st.secrets["NEO4J_USERNAME"], st.secrets["NEO4J_PASSWORD"])
    )
    
    return pc_index, neo4j_driver


def upload_to_s3(file_obj):
    """
    Directly upload file from Streamlit to S3.
    """
    try:
        user_email = st.session_state.get('user_email','unknown')
        unique_id = str(uuid.uuid4())[:8]
        clean_filename = file_obj.name.replace(" ","_")
        key = f"documents/{user_email}/{unique_id}_{clean_filename}"
        
        file_obj.seek(0)
        
        st.session_state.s3_client.upload_fileobj(
            file_obj,
            BUCKET_NAME,
            key,
            ExtraArgs={
                'ContentType': 'application/pdf',
                'Tagging': 'status=uploaded'
            }
        )
        
        return True, "File uploaded, waiting for indexer...", key
    
    except Exception as e:
        return False, f"Upload failed: {str(e)}", None
    
def get_presigned_url(key):
    """Generates a temporary url to view the file"""
    try:
        url = st.session_state.s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket':BUCKET_NAME, 'Key':key
            },
            ExpiresIn=300
        )
        return url
    except Exception as e:
        st.error(f"Error: {e}")
        return None
    
def delete_file(key):
    """Deletes file from S3 -> Pinecone -> Neo4j (Bare Metal)"""
    user_email = st.session_state.get('user_email')
    if not user_email:
        st.error("User email not found in session.")
        return False
    
    expected_prefix = f"documents/{user_email}/"
    
    if not key.startswith(expected_prefix):
        st.error(f"Authorization Error: You do not own this file.\nTarget: {key}\nYou: {user_email}")
        return False
    
    # Get bare-metal clients
    pc_index, neo4j_driver = init_db_connections()
    
    status_msg = []
    success = True
    
    # 1. S3 Delete
    try:
        st.session_state.s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=key
        )
        status_msg.append("S3 file deleted")
    except Exception as e:
        st.error(f"S3 delete failed: {e}")
        return False    
    
    # 2. Pinecone Delete (Direct API)
    try:
        # Pinecone's delete_by_filter logic
        pc_index.delete(
            filter={"source": key},
            namespace=user_email
        )
        status_msg.append("Vectors deleted")
    except Exception as e:
        print(f"Vector delete warning: {e}")
        status_msg.append("Vector cleanup failed")
        success = False     
    
    # 3. Neo4j Delete (Direct Driver)
    try:
        query = """
            MATCH (d:Document) 
            WHERE d.source = $key 
            DETACH DELETE d
        """
        with neo4j_driver.session() as session:
            session.run(query, key=key)
            
        status_msg.append("Graph nodes deleted")
    except Exception as e:
        print(f"Graph delete warning: {e}")
        status_msg.append("Graph cleanup failed")
        success = False
    
    # Summary
    if success:
        st.toast(" | ".join(status_msg))
    else:
        st.warning("Partial delete: " + " | ".join(status_msg))
        
    return True
            

def poll_indexing_status(bucket_name, file_key, timeout=90, interval=5):
    """
    Polls S3 every 'interval' seconds to check if the status tag becomes 'ready'.
    Stops after 'timeout' seconds.
    """
    start_time = time.time()
    
    status_container = st.empty()
    progress_bar = status_container.progress(0, text="Waiting for indexer to start...")
    
    while (time.time() - start_time) < timeout:
        try:
            response = st.session_state.s3_client.get_object_tagging(
                Bucket=bucket_name,
                Key=file_key
            )
            
            # Extract tags into a dict
            tags = {t['Key']: t['Value'] for t in response.get('TagSet', [])}
            status = tags.get('status', 'unknown')
            
            if status == 'ready':
                progress_bar.progress(100, text="Indexing Complete!")
                time.sleep(1)
                status_container.empty()
                return True
            
            elif status == 'failed':
                status_container.error("❌ Indexing Failed in Lambda.")
                return False
            
            elif status == 'indexing':
                progress_bar.progress(50, text="AI is ingesting your document(s)...")
            
            # Wait before next check
            time.sleep(interval)
            
        except Exception as e:
            time.sleep(interval)
            
    status_container.error("Timeout: Indexing took too long.")
    return False

def show_document_sidebar():
    st.sidebar.header("Your Documents")
    
    user_email = st.session_state.get('user_email')
    if not user_email: return

    #Fetch list of files
    try:
        response = st.session_state.s3_client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=f"documents/{user_email}/"
        )
    except Exception:
        st.sidebar.error("Could not fetch file list")
        return

    if 'Contents' not in response:
        st.sidebar.caption("No documents uploaded.")
        return

    if st.sidebar.button("Refresh Status"):
        st.rerun()
    
    #Iterate files
    for obj in response['Contents']:
        key = obj['Key']
        # Remove the UUID prefix (first 9 chars usually: "uuid_")
        filename = key.split('_', 1)[-1] 
        
        # Fetch Tag (Status)
        try:
            tags = st.session_state.s3_client.get_object_tagging(Bucket=BUCKET_NAME, Key=key)
            status = next((t['Value'] for t in tags['TagSet'] if t['Key'] == 'status'), 'uploaded')
        except:
            status = 'unknown'

        # Icon Logic
        if status == 'uploaded': icon, color = "⏳", "orange"
        elif status == 'indexing': icon, color = "⚙️", "blue"
        elif status == 'ready': icon, color = "✅", "green"
        elif status == 'failed': icon, color = "❌", "red"
        else: icon, color = "❓", "grey"

        # Render in Sidebar
        col1, col2, col3 = st.sidebar.columns([0.15, 0.75,0.15])
        
        col1.write(icon)
        col2.caption(f":{color}[{filename} ({status.capitalize()})]")
        
        with col3:
            with st.popover("⋮", use_container_width=True):
                st.markdown(f"**{filename}**")
                
                # VIEW IN A NEW TAB
                url = get_presigned_url(key)
                if url:
                    st.link_button("View PDF", url, help="Open in new tab")
                
                # DELETE
                if st.button("Delete", key=f"del_{key}", type="primary"):
                    if delete_file(key):
                        st.success("Deleted!")
                        st.rerun()
                        
                # RETRY (If failed)
                if status == 'failed':
                    if st.button("Retry", key=f"retry_{key}"):
                        # Logic: Reset tag to 'uploaded' to re-trigger Lambda? 
                        # (Requires Lambda to listen to Tag changes, or just re-upload)
                        st.info("Re-upload to retry.")
    
def check_user_has_files(user_email):
    """Checks if the user has at least one file in S3."""
    try:
        bucket = st.secrets["S3_BUCKET_NAME"]
        prefix = f"documents/{user_email}/"
        
        # MaxKeys=1 makes this check super fast
        response = st.session_state.s3_client.list_objects_v2(
            Bucket=bucket, 
            Prefix=prefix, 
            MaxKeys=1
        )
        return 'Contents' in response
    except Exception:
        return False    