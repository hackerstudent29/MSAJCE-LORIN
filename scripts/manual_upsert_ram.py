import os, json, httpx, time
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
INDEX_NAME = "msajce-v2"

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

def get_embedding(text):
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"}
    data = {"model": "openai/text-embedding-3-small", "input": text}
    r = httpx.post("https://openrouter.ai/api/v1/embeddings", headers=headers, json=data, timeout=60)
    return r.json()["data"][0]["embedding"]

def upsert_profile():
    path = "data/knowledge_base/ramanathan_profile.json"
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    vectors = []
    
    for c in chunks:
        text = c["text"]
        print(f"Embedding chunk: {c['chunk_id']}")
        emb = get_embedding(text)
        
        metadata = {
            "text": text,
            "chunk_id": c["chunk_id"],
            "node_type": "FACT",
            "chunk_type": "profile",
            "priority": "critical",
            "department": "IT",
            "source_files": "ramanathan_profile.json",
            "entity_name": "Ramanathan S",
            "entity_role": "Lead AI Architect"
        }
        
        vectors.append({
            "id": c["chunk_id"],
            "values": emb,
            "metadata": metadata
        })

    index.upsert(vectors=vectors)
    print(f"Successfully upserted {len(vectors)} chunks for Ramanathan S.")

if __name__ == "__main__":
    upsert_profile()
