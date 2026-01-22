import sys,os 
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
if backend_dir not in sys.path:
    sys.path.append(backend_dir)
    
from shared.db_connect import get_graph_db, get_vector_db

def lambda_handler(event, context):
    vector_db = get_vector_db()
    graph_db = get_graph_db()
    print("success")

lambda_handler(None,None)    