# frontend/api.py
import requests
import streamlit as st
import os

# Hardcode for now, or use os.getenv("RAG_LAMBDA_URL")
LAMBDA_URL = "https://en3zsjq27skes32qd4hwwzk4xa0ognes.lambda-url.eu-west-1.on.aws/"

def format_history(streamlit_messages):
    """
    Converts Streamlit history [{'role': 'user', 'content': '...'}]
    to Gemini/Lambda history [{'role': 'user', 'parts': [{'text': '...'}]}]
    """
    gemini_history = []
    for msg in streamlit_messages:
        # Map 'assistant' -> 'model' for Gemini
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_history.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    return gemini_history

def query_rag_bot(question, user_email, message_history):
    """
    Sends request to Micro-RAG Lambda
    """
    # 1. Format the payload
    # Note: We send the *previous* history, excluding the current new question
    history_payload = format_history(message_history[:-1]) 
    
    payload = {
        "question": question,
        "user_email": user_email,
        "history": history_payload
    }

    try:
        # 2. Send Request
        response = requests.post(
            LAMBDA_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20 # Give Lambda time to think
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Error {response.status_code}: {response.text}"}
            
    except Exception as e:
        return {"error": f"Connection Failed: {str(e)}"}