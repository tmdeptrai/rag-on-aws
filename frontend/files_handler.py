import boto3
from botocore.config import Config
import uuid
import streamlit as st
import os, sys
from dotenv import load_dotenv
load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.db_connect import get_vector_db, get_graph_db

if 's3_client' not in st.session_state:
    st.session_state.s3_client = boto3.client(
        's3',
        region_name = os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(signature_version='s3v4')
    )
    
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")    

def get_cached_dbs():
    """
    Returns (vector_db, graph_db).
    Initializes them only if they aren't already in Session State.
    """
    if 'vector_db' not in st.session_state:
        with st.spinner("Connecting to Databases..."):
            st.session_state.vector_db = get_vector_db()
            st.session_state.graph_db = get_graph_db()
            
    return st.session_state.vector_db, st.session_state.graph_db

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
        
        return True, "File uploaded, waiting for indexer..."
    
    except Exception as e:
        return False, f"Upload failed: {str(e)}"
    
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
    """Deletes file from S3 -> Pinecone -> Neo4j"""
    user_email = st.session_state.get('user_email')
    if not user_email:
        st.error("User email not found in session.")
        return False
    
    vector_db, graph_db = get_cached_dbs()
    success = True
    status_msg = []
    try:
        st.session_state.s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=key
        )
        status_msg.append("S3 file deleted")
    except Exception as e:
        st.error(f"S3 delete failed: {e}")
        return False    
    
    #Delete from pinecone
    try:
        vector_db.index.delete(
            filter={
                "source": key,
            },
            namespace=user_email
        )
        
        status_msg.append("Vectors deleted")
    except Exception as e:
        print(f"Vector delete warning: {e}")
        status_msg.append("Vector cleanup failed")
        success = False     
    
    #Neo4j
    try:
        query = """
            MATCH (d:Document) 
            WHERE d.source = $key 
            DETACH DELETE d
        """
        graph_db.query(query,params={"key":key})
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

    st.sidebar.markdown("---")
    
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
    