import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

def wipe_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = "quickstart"
    
    if index_name in [idx.name for idx in pc.list_indexes()]:
        print(f"Wiping all data from Pinecone index: {index_name}")
        index = pc.Index(index_name)
        index.delete(delete_all=True)
        print("Success: Index wiped.")
    else:
        print(f"Error: Index {index_name} not found.")

if __name__ == "__main__":
    wipe_index()
