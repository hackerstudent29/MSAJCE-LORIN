from pinecone import Pinecone
import os
from dotenv import load_dotenv
import requests

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("quickstart")

def search_pinecone(query_text):
    print(f"Searching Pinecone for: {query_text}")
    # Get embedding from OpenRouter
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    data = {"model": "openai/text-embedding-3-small", "input": query_text}
    resp = requests.post("https://openrouter.ai/api/v1/embeddings", headers=headers, json=data).json()
    q_vector = resp["data"][0]["embedding"]
    
    results = index.query(vector=q_vector, top_k=5, include_metadata=True)
    for i, match in enumerate(results['matches']):
        print(f"\nMatch {i+1} (Score: {match['score']}):")
        print(f"Text: {match['metadata'].get('text', '')[:200]}...")
        print(f"Section: {match['metadata'].get('section', '')}")

if __name__ == "__main__":
    search_pinecone("who is usha")
    search_pinecone("Mrs. S. Usha")
