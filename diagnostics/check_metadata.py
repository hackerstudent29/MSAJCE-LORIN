import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("quickstart")

# Fetch one vector
results = index.query(vector=[0]*1536, top_k=1, include_metadata=True)
print(results['matches'][0]['metadata'].keys())
print(results['matches'][0]['metadata'])
