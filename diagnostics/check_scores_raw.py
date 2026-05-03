import os
import sys
from dotenv import load_dotenv
from pinecone import Pinecone
import requests

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def check_scores(query):
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("quickstart")
    
    # Get embedding
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}", "Content-Type": "application/json"}
    data = {"model": "openai/text-embedding-3-small", "input": query}
    q_vector = requests.post("https://openrouter.ai/api/v1/embeddings", headers=headers, json=data).json()["data"][0]["embedding"]
    
    # Pinecone results
    results = index.query(vector=q_vector, top_k=5, include_metadata=True)
    print(f"\nQuery: {query}")
    print("Pinecone Top Scores:")
    for match in results['matches']:
        print(f"  Score: {match['score']:.4f} | Text: {match['metadata']['text'][:100]}...")

if __name__ == "__main__":
    check_scores("Usha")
    check_scores("who is usha")
