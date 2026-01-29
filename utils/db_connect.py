"""Connect to Pinecone and Neo4j vector databases"""
import os
from dotenv import load_dotenv
load_dotenv()

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_neo4j import Neo4jGraph
# from pipecone
def get_vector_db():
    """
    Establishes connection to Pinecone and Gemini Embeddings
    Returns VectorStore object
    """
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        api_key = os.getenv("GOOGLE_API_KEY"),
    )
    vector_store = PineconeVectorStore(
        index_name=os.getenv("PINECONE_INDEX_NAME"),
        pinecone_api_key=os.getenv("PINECONE_API_KEY"),
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
        print("Successfully connected to Pinecone vector store!")
        
    graph_db = get_graph_db()
    if graph_db:
        print("Successfully connected to Neo4j graph database!")
        
            