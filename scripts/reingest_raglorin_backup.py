import os
import json
import time
import requests
from pinecone import Pinecone
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
EMBEDDING_MODEL = "openai/text-embedding-3-small"
INDEX_NAME = "raglorin-backup"
JSON_DIR = r"d:\.gemini\claude RAG\data\knowledge_base"

def get_embedding(text):
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": EMBEDDING_MODEL,
        "input": text
    }
    for _ in range(3):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            else:
                print(f"Error getting embedding: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Embedding error: {e}")
        time.sleep(1)
    return None

def process_ingestion():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    
    # Optional: Wipe index before reingesting?
    # index.delete(delete_all=True)
    # print(f"Wiped {INDEX_NAME} index.")

    all_chunks = []
    print("Reading JSON files from knowledge_base...")
    for filename in os.listdir(JSON_DIR):
        if not filename.endswith(".json") or filename == "unified_master_chunks.json" or "alumni_lists" in filename:
            continue
            
        path = os.path.join(JSON_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Check if it's the right format (with metadata and chunks)
            if "metadata" not in data or "chunks" not in data:
                continue
                
            global_metadata = data["metadata"]
            institution = global_metadata.get("institution", "MSAJCE")
            page_title = global_metadata.get("page_title", "")
            last_updated = global_metadata.get("scraped_date", "2026-05-01")
            
            for chunk in data.get("chunks", []):
                chunk_id = chunk.get("chunk_id", "")
                text = chunk.get("text", "")
                section = chunk.get("section", "")
                source_url = chunk.get("source_url", global_metadata.get("source_url", ""))
                
                # Format keywords
                keywords_list = chunk.get("keywords", [])
                keywords = ", ".join(keywords_list) if isinstance(keywords_list, list) else str(keywords_list)
                
                # Format entities
                entities_data = chunk.get("entities", {})
                entities_str = json.dumps(entities_data)
                
                # Super-chunk embedding text (similar to unified_ingestor)
                embed_text = f"SECTION: {section}\nKEYWORDS: {keywords}\n\nCONTENT:\n{text}"
                
                metadata = {
                    "chunk_id": chunk_id,
                    "entities": entities_str,
                    "institution": institution,
                    "keywords": keywords,
                    "last_updated": last_updated,
                    "page_title": page_title,
                    "section": section,
                    "source_url": source_url,
                    "text": text
                }
                
                all_chunks.append({
                    "id": chunk_id,
                    "embed_text": embed_text,
                    "metadata": metadata
                })
    
    print(f"Found {len(all_chunks)} chunks to process.")
    
    # Pinecone Ingestion
    print(f"Ingesting to Pinecone {INDEX_NAME}...")
    vectors = []
    
    for i, chunk in enumerate(tqdm(all_chunks)):
        vector = get_embedding(chunk["embed_text"])
        if vector:
            vectors.append({
                "id": chunk["id"],
                "values": vector,
                "metadata": chunk["metadata"]
            })
            
        if len(vectors) >= 50:
            index.upsert(vectors=vectors)
            vectors = []
            time.sleep(0.5)
            
    if vectors:
        index.upsert(vectors=vectors)

    print("Re-ingestion Complete using old schema.")

if __name__ == "__main__":
    process_ingestion()
