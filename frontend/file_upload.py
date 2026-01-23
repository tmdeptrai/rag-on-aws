import boto3
import uuid
import streamlit as st
import os
from dotenv import load_dotenv
load_dotenv()

if 's3_client' not in st.session_state:
    st.session_state.s3_client = boto3.client(
        's3',
        region_name = os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")    

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
    

def show_document_sidebar():
    st.sidebar.header("Your Documents")
    
    user_email = st.session_state.get('user_email')
    if not user_email: return

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

    for obj in response['Contents']:
        key = obj['Key']
        # Remove the UUID prefix (first 9 chars usually: "uuid_")
        filename = key.split('_', 1)[-1] 
        
        # Fetch Tag (Status)
        try:
            tags = st.session_state.s3_client.get_object_tagging(
                Bucket=BUCKET_NAME, Key=key
            )
            status = 'uploaded' 
            for tag in tags['TagSet']:
                if tag['Key'] == 'status':
                    status = tag['Value']
        except:
            status = 'unknown'

        # Map Status to Icons & Colors
        if status == 'uploaded':
            icon = "⏳"
            color = "orange"
        elif status == 'indexing':
            icon = "⚙️"
            color = "blue"
        elif status == 'ready':
            icon = "✅"
            color = "green"
        elif status == 'failed':
            icon = "❌"
            color = "red"
        else:
            icon = "❓"
            color = "grey"

        # Render in Sidebar
        col1, col2 = st.sidebar.columns([0.15, 0.85])
        
        col1.write(icon)
        col2.caption(f":{color}[{filename} ({status.capitalize()})]")
    