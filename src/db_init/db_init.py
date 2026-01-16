"""
idk, a Lambda function to set up connection to an Upstash vector database?
"""
import os
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores.upstash import UpstashVectorStore

def get_vector_db():
    """
    Establishes connection to Upstash and Gemini Embeddings
    Returns VectorStore object
    """
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        api_key = os.getenv("GOOGLE_API_KEY")
    )
    vector_store = UpstashVectorStore(
        index_url=os.getenv("UPSTASH_VECTOR_REST_URL"),
        index_token=os.getenv("UPSTASH_VECTOR_REST_TOKEN"),
        embedding=embeddings
    )
    return vector_store

if __name__ == "__main__":
    vector_db = get_vector_db()
    if vector_db:
        print("Successfully connected to Upstash vector store!")
