import os
import requests
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
INDEX_NAME = "raglorin-backup"

def get_embedding(text):
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "openai/text-embedding-3-small", "input": text}
    resp = requests.post(url, headers=headers, json=data)
    return resp.json()["data"][0]["embedding"]

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

text = """
Faculty — Department of Information Technology, MSAJCE
Academic Year 2023-2024:
1 | Dr. KANNAN S | Professor | 31/08/2022 | M.E., Ph.D. | Regular
2 | Dr. WESLIN D | Associate Professor | 14/12/2020 | M.E., Ph.D. | Regular
3 | Dr. PRAKASH D | Associate Professor | 15/06/2023 | Ph.D | Regular
"""

metadata = {
    "chunk_id": "manual_patch_weslin",
    "institution": "MSAJCE",
    "page_title": "Information Technology Department Faculty",
    "section": "Faculty Details 2023-2024",
    "text": text,
    "last_updated": "2026-05-09",
    "priority": "high",
    "entity_professor": "Dr. Weslin D"
}

emb = get_embedding(f"SECTION: Faculty Details\nCONTENT: {text}")
index.upsert(vectors=[{"id": "manual_patch_weslin", "values": emb, "metadata": metadata}])
print("Manual patch for Weslin complete.")
