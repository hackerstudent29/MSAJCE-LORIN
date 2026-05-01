import os
import json
import time
import httpx
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# CONFIG
INDEX_NAME = "raglorin"
DATA_PATH = "data/unified_chunks.json"
EMBEDDING_MODEL = "text-embedding-3-small"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

def get_embeddings(texts):
    """Fetch embeddings from OpenRouter."""
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    payload = {"model": EMBEDDING_MODEL, "input": texts}
    
    with httpx.Client() as client:
        res = client.post(OPENROUTER_EMBED_URL, headers=headers, json=payload, timeout=60.0)
        res.raise_for_status()
        return [item["embedding"] for item in res.json()["data"]]

def index_institutional_data():
    print(f"Starting Indexing for '{INDEX_NAME}'...")
    
    # 1. Init Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(INDEX_NAME)
    
    # 2. Load Chunks
    if not os.path.exists(DATA_PATH):
        print(f"Error: {DATA_PATH} not found!")
        return
        
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    
    print(f"Loaded {len(chunks)} chunks from {DATA_PATH}.")
    
    # 3. Batch Indexing (Pinecone prefers batches)
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        
        # RESILIENT EXTRACTION: Filter out chunks with no text
        valid_batch = [c for c in batch if c.get("text") and len(c.get("text", "").strip()) > 10]
        if not valid_batch:
            print(f"Skipping batch {i//batch_size + 1}: No valid text content found.")
            continue
            
        texts = [c["text"] for c in valid_batch]
        
        print(f"Processing batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1} ({len(valid_batch)} chunks)...")
        
        try:
            embeddings = get_embeddings(texts)
            
            vectors = []
            for j, chunk in enumerate(valid_batch):
                vectors.append({
                    "id": chunk.get("chunk_id", f"gen_{i+j}"),
                    "values": embeddings[j],
                    "metadata": {
                        "text": chunk["text"],
                        "source": chunk.get("source_file", chunk.get("source", "unknown")),
                        "category": chunk.get("category", "general")
                    }
                })
            
            index.upsert(vectors=vectors)
            print(f"Upserted {len(vectors)} vectors.")
            
        except Exception as e:
            print(f"Batch Error: {e}")
            continue
            
    print("\nIndexing Complete! Your 'raglorin' index is now live.")

if __name__ == "__main__":
    index_institutional_data()
