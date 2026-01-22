"""Connect to Upstash and Neo4j vector databases"""
import os
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores.upstash import UpstashVectorStore
from langchain_neo4j import Neo4jGraph

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

def get_graph_db():
    """
    Connect to Neo4j on AuraDB
    """
    graph_db = Neo4jGraph(
        url=os.getenv("NEO4J_URI"),
        username = os.getenv("NEO4J_USERNAME"),
        password= os.getenv("NEO4J_PASSWORD")
    )
    return graph_db

if __name__ == "__main__":
    vector_db = get_vector_db()
    if vector_db:
        print("Successfully connected to Upstash vector store!")
        
    graph_db = get_graph_db()
    if graph_db:
        print("Successfully connected to Neo4j graph database!")
        
            
