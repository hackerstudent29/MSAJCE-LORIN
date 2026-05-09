import os
import json
import time
import hashlib
import re
import requests
from pinecone import Pinecone
from dotenv import load_dotenv
from tqdm import tqdm
import bm25s
import Stemmer

load_dotenv()

# Configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
INDEX_NAME = "raglorin-backup"
MD_DIR = r"d:\.gemini\claude RAG\data\datalab md"
JSON_DIR = r"d:\.gemini\claude RAG\data\knowledge_base"
BM25_INDEX_PATH = r"d:\.gemini\claude RAG\data\bm25_index"

def get_embedding(text):
    url = "https://openrouter.ai/api/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/text-embedding-3-small",
        "input": text
    }
    for _ in range(3):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
        except: pass
        time.sleep(1)
    return None

def chunk_markdown(text, filename):
    # Simple chunking by headers or double newlines
    sections = re.split(r'\n(?=# )|\n(?=## )', text)
    chunks = []
    for i, sec in enumerate(sections):
        if not sec.strip(): continue
        lines = sec.strip().split('\n')
        title = lines[0].strip('# ')
        content = '\n'.join(lines[1:]).strip()
        
        # Split large sections
        if len(content) > 2000:
            parts = [content[i:i+2000] for i in range(0, len(content), 1800)]
            for j, p in enumerate(parts):
                chunks.append({
                    "id": f"{filename}_{i}_{j}",
                    "text": p,
                    "section": f"{title} (Part {j+1})"
                })
        else:
            chunks.append({
                "id": f"{filename}_{i}",
                "text": content,
                "section": title
            })
    return chunks

def run_ingestion():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    
    all_chunks = []
    
    # 1. Process Markdown Files (The 23 PDFs)
    print("Processing Markdown files...")
    for filename in os.listdir(MD_DIR):
        if not filename.endswith(".md"): continue
        path = os.path.join(MD_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
            chunks = chunk_markdown(text, filename)
            for c in chunks:
                metadata = {
                    "chunk_id": c["id"],
                    "institution": "MSAJCE",
                    "page_title": filename.replace('.md', ''),
                    "section": c["section"],
                    "text": c["text"],
                    "last_updated": "2026-05-09",
                    "priority": "medium",
                    "source_url": ""
                }
                all_chunks.append({"id": c["id"], "text": c["text"], "metadata": metadata})

    # 2. Process JSON Files (Institutional Knowledge)
    print("Processing JSON files...")
    for filename in os.listdir(JSON_DIR):
        if not filename.endswith(".json") or filename == "unified_master_chunks.json": continue
        path = os.path.join(JSON_DIR, filename)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "chunks" in data:
                global_meta = data.get("metadata", {})
                for i, chunk in enumerate(data["chunks"]):
                    cid = chunk.get("chunk_id", f"{filename}_{i}")
                    text = chunk.get("text", "")
                    metadata = {
                        "chunk_id": cid,
                        "institution": global_meta.get("institution", "MSAJCE"),
                        "page_title": global_meta.get("page_title", filename),
                        "section": chunk.get("section", "General"),
                        "text": text,
                        "last_updated": "2026-05-09",
                        "priority": chunk.get("priority", "medium")
                    }
                    all_chunks.append({"id": cid, "text": text, "metadata": metadata})

    print(f"Total chunks to ingest: {len(all_chunks)}")
    
    # Wipe index first
    print("Clearing index...")
    try: index.delete(delete_all=True)
    except: pass
    
    # Pinecone Upsert
    print("Upserting to Pinecone...")
    vectors = []
    for chunk in tqdm(all_chunks):
        # Contextual embedding
        embed_text = f"SECTION: {chunk['metadata']['section']}\nCONTENT: {chunk['text']}"
        emb = get_embedding(embed_text)
        if emb:
            vectors.append({"id": chunk["id"], "values": emb, "metadata": chunk["metadata"]})
        
        if len(vectors) >= 50:
            index.upsert(vectors=vectors)
            vectors = []
            time.sleep(0.5)
    if vectors: index.upsert(vectors=vectors)

    # BM25 Update
    print("Building BM25 index...")
    stemmer = Stemmer.Stemmer("english")
    corpus = [c["text"] for c in all_chunks]
    metadata_list = [c["metadata"] for c in all_chunks]
    tokens = bm25s.tokenize(corpus, stemmer=stemmer)
    retriever = bm25s.BM25(corpus=metadata_list)
    retriever.index(tokens)
    if not os.path.exists(BM25_INDEX_PATH): os.makedirs(BM25_INDEX_PATH)
    retriever.save(BM25_INDEX_PATH, corpus=metadata_list)
    
    print("FULL RE-INGESTION COMPLETE.")

if __name__ == "__main__":
    run_ingestion()
