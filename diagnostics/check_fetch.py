import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("quickstart")

# Fetch by ID
res = index.fetch(ids=["msajce_about_chunk_05"])
print(res)
