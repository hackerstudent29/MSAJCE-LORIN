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

def upsert_csi_leaders():
    leaders = [
        {"id": "entity_yogesh_r", "name": "Yogesh R", "role": "President of CSI", "dept": "IT", "batch": "2022-2026", "text": "Yogesh R is the President of the Computer Society of India (CSI) student chapter at MSAJCE. He is from the IT department, 2022-2026 batch."},
        {"id": "entity_saqlin_mustaq", "name": "Saqlin Mustaq M", "role": "Vice President of CSI", "dept": "AI&DS", "batch": "2023-2027", "text": "Saqlin Mustaq M is the Vice President of the Computer Society of India (CSI) at MSAJCE. He belongs to the AI&DS department, 2023-2027 batch."},
        {"id": "entity_abu_jabar", "name": "Abu Jabar Mubarak", "role": "Secretary of CSI", "dept": "CS&BS", "batch": "2022-2026", "text": "Abu Jabar Mubarak is the Secretary of the Computer Society of India (CSI) at MSAJCE. He is a student of the CS&BS department, 2022-2026 batch."}
    ]
    
    vectors = []
    for l in leaders:
        print(f"Embedding: {l['name']}")
        emb = get_embedding(l['text'])
        metadata = {
            "text": l["text"],
            "chunk_id": l["id"],
            "node_type": "PERSON",
            "chunk_type": "profile",
            "priority": "critical",
            "department": l["dept"],
            "entity_name": l["name"],
            "entity_role": l["role"],
            "keywords": f"{l['name']}, CSI, President, Student Leader"
        }
        vectors.append({"id": l["id"], "values": emb, "metadata": metadata})

    index.upsert(vectors=vectors)
    print(f"Successfully upserted {len(vectors)} CSI leaders.")

if __name__ == "__main__":
    upsert_csi_leaders()
