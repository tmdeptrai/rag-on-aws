import requests
import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
def load_secrets_to_env():
    for key, value in st.secrets.items():
        if key not in os.environ:
            os.environ[key] = str(value)
load_secrets_to_env()

QUERY_LAMBDA_URL = os.getenv("QUERY_LAMBDA_URL")

def query_rag_bot(question, user_email):
    """
    Sends a Single-Turn request to Lambda endpoint for query.
    No history is sent, saving tokens and complexity.
    """
    payload = {
        "question": question,
        "user_email": user_email
    }

    try:
        response = requests.post(
            QUERY_LAMBDA_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20 
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Error {response.status_code}: {response.text}"}
            
    except Exception as e:
        return {"error": f"Connection Failed: {str(e)}"}