import os
import json
import time
import httpx
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# CONFIG
INDEX_NAME = "raglorin"
TRANSPORT_JSON = r"d:\.gemini\claude RAG\data\knowledge_base\page_04_transport.json"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

def get_embeddings(texts):
    """Fetch embeddings from OpenRouter."""
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}
    payload = {"model": EMBEDDING_MODEL, "input": texts}
    
    with httpx.Client() as client:
        res = client.post(OPENROUTER_EMBED_URL, headers=headers, json=payload, timeout=60.0)
        res.raise_for_status()
        return [item["embedding"] for item in res.json()["data"]]

def inject_transport_only():
    print(f"Starting Targeted Ingestion for transport chunks into '{INDEX_NAME}'...")
    
    # 1. Init Pinecone
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(INDEX_NAME)
    
    # 2. Load Chunks
    if not os.path.exists(TRANSPORT_JSON):
        print(f"Error: {TRANSPORT_JSON} not found!")
        return
        
    with open(TRANSPORT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
        chunks = data.get("chunks", [])
    
    print(f"Loaded {len(chunks)} chunks from {TRANSPORT_JSON}.")
    
    # Process in one batch (only 12 chunks)
    valid_chunks = [c for c in chunks if c.get("content") and len(c.get("content", "").strip()) > 10]
    if not valid_chunks:
        print("No valid chunks found.")
        return
        
    texts = []
    for c in valid_chunks:
        # Build the same super-chunk text as in ingest_pinecone.py for consistency
        section = c.get('section', 'General')
        possible_questions = "\n".join(c.get('possible_questions', []))
        content = c.get('content', '')
        keywords = ", ".join(c.get('keywords', []))
        
        super_text = (
            f"SECTION: {section}\n"
            f"QUESTIONS: {possible_questions}\n"
            f"CONTENT: {content}\n"
            f"KEYWORDS: {keywords}"
        )
        texts.append(super_text)
    
    print(f"Generating embeddings for {len(valid_chunks)} chunks...")
    try:
        embeddings = get_embeddings(texts)
        
        vectors = []
        for j, chunk in enumerate(valid_chunks):
            vectors.append({
                "id": chunk["chunk_id"],
                "values": embeddings[j],
                "metadata": {
                    "text": chunk["content"],
                    "source_file": "page_04_transport.json",
                    "section": chunk.get("section", "General"),
                    "chunk_type": "fact", # Default for transport
                    "keywords": ", ".join(chunk.get("keywords", []))
                }
            })
        
        index.upsert(vectors=vectors)
        print(f"Successfully upserted {len(vectors)} transport vectors to Pinecone.")
        
    except Exception as e:
        print(f"Injection Error: {e}")

if __name__ == "__main__":
    inject_transport_only()
