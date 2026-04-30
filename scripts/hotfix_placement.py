import os
import json
import time
import requests
import bm25s
import Stemmer
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
INDEX_NAME = "quickstart"
OPENROUTER_EMBED_URL = "https://openrouter.ai/api/v1/embeddings"

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BM25_INDEX_PATH = os.path.join(ROOT_DIR, "data", "bm25_index")
JSON_DIR = os.path.join(ROOT_DIR, "data", "RAG Essentials", "rag jsons")

def get_embedding(text):
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "openai/text-embedding-3-small", "input": text}
    response = requests.post(OPENROUTER_EMBED_URL, headers=headers, json=data)
    if response.status_code != 200: raise Exception(f"Embedding Error: {response.text}")
    return response.json()["data"][0]["embedding"]

def hotfix():
    print("Starting Placement Hotfix...")
    
    # 1. Update Pinecone for the specific chunk
    placement_json_path = os.path.join(JSON_DIR, "msajce_placement.json")
    with open(placement_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chunk = data["chunks"][0] # msajce_placement_chunk_01
    content = chunk["text"]
    section = chunk["section"]
    summary = chunk["context"]
    questions = "\n".join(chunk["possible_questions"])
    
    super_text = f"SECTION: {section}\nSUMMARY: {summary}\nQUESTIONS: {questions}\nCONTENT: {content}"
    embedding = get_embedding(super_text)
    
    metadata = {
        "chunk_id": chunk["chunk_id"],
        "institution": "MSAJCE",
        "page_title": "Placement Cell",
        "section": section,
        "text": content,
        "source_url": chunk["source_url"],
        "keywords": ", ".join(chunk["keywords"]),
        "entities": json.dumps(chunk["entities"]),
        "last_updated": time.strftime("%Y-%m-%d")
    }
    
    index.upsert(vectors=[{"id": chunk["chunk_id"], "values": embedding, "metadata": metadata}])
    print("Pinecone Upserted.")

    # 2. Rebuild BM25 Index for ALL files (to ensure Vinodh is found by lexical search too)
    print("Rebuilding BM25 Index...")
    all_metadata = []
    all_corpus_texts = []
    
    for filename in os.listdir(JSON_DIR):
        if not filename.endswith(".json"): continue
        with open(os.path.join(JSON_DIR, filename), 'r', encoding='utf-8') as f:
            j_data = json.load(f)
            for c in j_data.get("chunks", []):
                txt = c.get("text") or c.get("content")
                if not txt: continue
                all_corpus_texts.append(f"SECTION: {c.get('section', 'General')}\nCONTENT: {txt}")
                all_metadata.append({
                    "chunk_id": c.get("chunk_id", ""),
                    "text": txt,
                    "section": c.get("section", "General"),
                    "source_url": c.get("source_url", "")
                })

    stemmer = Stemmer.Stemmer("english")
    corpus_tokens = bm25s.tokenize(all_corpus_texts, stemmer=stemmer)
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)
    retriever.save(BM25_INDEX_PATH, corpus=all_metadata)
    print("BM25 Index Rebuilt.")

if __name__ == "__main__":
    hotfix()
