import os
import re
import json
import httpx
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

# CONFIG
INDEX_NAMES = ["final-secret-rag", "claude-md-files"]
TRANSPORT_MD = r"d:\.gemini\claude RAG\data\datalab md\msajce_transport.md"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

def get_embeddings(texts):
    """Fetch embeddings from Vercel AI Gateway."""
    key = os.getenv("AI_GATEWAY_API_KEY")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {"model": "openai/text-embedding-3-small", "input": texts}
    
    url = "https://ai-gateway.vercel.sh/v1/embeddings"
    with httpx.Client() as client:
        res = client.post(url, headers=headers, json=payload, timeout=60.0)
        res.raise_for_status()
        return [item["embedding"] for item in res.json()["data"]]

def fix_transport_index():
    print(f"🚀 Starting Targeted Fix for transport chunks...")
    
    if not os.path.exists(TRANSPORT_MD):
        print(f"❌ Error: {TRANSPORT_MD} not found!")
        return

    with open(TRANSPORT_MD, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by Bus Route headers
    routes = re.split(r'### Bus Route:', content)
    chunks = []
    
    for i, route_text in enumerate(routes):
        if not route_text.strip(): continue
        
        # Extract route name (e.g. AR 8 — Manjambakkam)
        lines = route_text.strip().split("\n")
        route_header = lines[0].strip()
        
        # The first part of 'routes' list might be the file header, so handle it
        if "###" in route_text or "Bus Route" not in route_text:
            # This is likely a sub-header or the initial header
            full_text = "### Bus Route:" + route_text
        else:
            full_text = "### Bus Route:" + route_text

        # Create a unique chunk ID
        chunk_id = f"transport_fix_v2_{i}"
        
        # Clean the text for embedding
        clean_text = full_text.strip()
        
        chunks.append({
            "id": chunk_id,
            "text": clean_text,
            "metadata": {
                "text": clean_text,
                "source_file": "msajce_transport.md",
                "page_title": f"Transport Route: {route_header}",
                "topic": "transport",
                "chunk_type": "detailed_table",
                "last_updated": "2026-05-13"
            }
        })

    print(f"📦 Prepared {len(chunks)} route-based chunks.")

    # Embed and Upsert
    texts = [c["text"] for c in chunks]
    try:
        print(f"🧠 Generating embeddings...")
        embeddings = get_embeddings(texts)
        
        vectors = []
        for j, chunk in enumerate(chunks):
            vectors.append({
                "id": chunk["id"],
                "values": embeddings[j],
                "metadata": chunk["metadata"]
            })

        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        
        for idx_name in INDEX_NAMES:
            print(f"📡 Upserting to {idx_name}...")
            index = pc.Index(idx_name)
            index.upsert(vectors=vectors)
            print(f"✅ Success for {idx_name}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_transport_index()
