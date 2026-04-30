import os
import json
import glob
import time
import requests
import bm25s
import Stemmer
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

# Configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
INDEX_NAME = "quickstart"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

# Initialize Clients
pc = Pinecone(api_key=PINECONE_API_KEY)

# Use Absolute Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
BM25_INDEX_PATH = os.path.join(ROOT_DIR, "data", "bm25_index")

def get_embedding(text):
    """Generates 1536-dim embedding using OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/text-embedding-3-small",
        "input": text
    }
    response = requests.post(OPENROUTER_EMBED_URL, headers=headers, json=data)
    if response.status_code != 200:
        raise Exception(f"OpenRouter Embedding Error: {response.text}")
    return response.json()["data"][0]["embedding"]

def ingest_data():
    """Production Ingestion Pipeline (OpenRouter 1536-dim + BM25)."""
    json_path = os.path.join(ROOT_DIR, "data", "jsons", "*.json")
    files = glob.glob(json_path)
    
    all_corpus_texts = []
    all_metadata = []
    
    index = pc.Index(INDEX_NAME)
    print("Clearing Pinecone (1536 dims)...")
    try:
        index.delete(delete_all=True)
    except: pass

    for file_path in files:
        print(f"Processing {os.path.basename(file_path)}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            chunks = data.get("chunks", [])
            
            vectors = []
            for chunk in chunks:
                content = chunk.get("text") or chunk.get("content")
                if not content: continue
                
                section = chunk.get('section', 'General')
                context_summary = chunk.get('context', '')
                possible_questions = "\n".join(chunk.get('possible_questions', []))
                
                super_chunk_text = (
                    f"SECTION: {section}\n"
                    f"SUMMARY: {context_summary}\n"
                    f"QUESTIONS: {possible_questions}\n"
                    f"CONTENT: {content}"
                )
                
                # No sleep - OpenRouter is fast
                embedding = get_embedding(super_chunk_text)
                
                metadata = {
                    "chunk_id": chunk.get("chunk_id", ""),
                    "institution": data.get("metadata", {}).get("institution", "MSAJCE"),
                    "page_title": data.get("metadata", {}).get("page_title", os.path.basename(file_path)),
                    "section": chunk.get("section", "General"),
                    "text": content,
                    "source_url": chunk.get("source_url", ""),
                    "keywords": ", ".join(chunk.get("keywords", [])),
                    "entities": json.dumps(chunk.get("entities", {})),
                    "last_updated": time.strftime("%Y-%m-%d")
                }
                
                vectors.append({"id": chunk["chunk_id"], "values": embedding, "metadata": metadata})
                all_corpus_texts.append(super_chunk_text)
                all_metadata.append(metadata)
            
            if vectors:
                index.upsert(vectors=vectors)
                print(f"  Upserted {len(vectors)} vectors.")

    print("\nBuilding BM25 Index...")
    stemmer = Stemmer.Stemmer("english")
    corpus_tokens = bm25s.tokenize(all_corpus_texts, stemmer=stemmer)
    
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)
    
    if not os.path.exists(BM25_INDEX_PATH): os.makedirs(BM25_INDEX_PATH)
    retriever.save(BM25_INDEX_PATH, corpus=all_metadata)
    print(f"Production Ingestion Complete (BM25 + OpenRouter 1536-dim)")

if __name__ == "__main__":
    # STRICT 1536 Dimension Reset
    print("Resetting Pinecone index to STRICT 1536 dimensions...")
    if INDEX_NAME in pc.list_indexes().names():
        pc.delete_index(INDEX_NAME)
        while INDEX_NAME in pc.list_indexes().names(): time.sleep(1)
    
    pc.create_index(
        name=INDEX_NAME,
        dimension=1536,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
    while not pc.describe_index(INDEX_NAME).status['ready']: time.sleep(1)
    
    ingest_data()
