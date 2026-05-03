import os
from pinecone import Pinecone
from dotenv import load_dotenv

def audit_pinecone():
    load_dotenv()
    pc_key = os.getenv("PINECONE_API_KEY")
    if not pc_key:
        print("Missing PINECONE_API_KEY")
        return
    
    pc = Pinecone(api_key=pc_key)
    print("Checking Pinecone Indexes...")
    indexes = pc.list_indexes()
    for idx in indexes:
        print(f"Index Name: {idx.name}")
        print(f"Dimension: {idx.dimension}")
        print(f"Status: {idx.status['state']}")
        
        # Check stats
        index = pc.Index(idx.name)
        stats = index.describe_index_stats()
        print(f"Total Vectors: {stats.total_vector_count}")
        print("-" * 20)

if __name__ == "__main__":
    audit_pinecone()
