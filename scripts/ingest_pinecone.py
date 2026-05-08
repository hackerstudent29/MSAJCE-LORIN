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
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "raglorin")
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
    res_json = response.json()
    if "data" not in res_json:
        print(f"DEBUG: OpenRouter Response: {res_json}")
        raise Exception(f"OpenRouter Error: Missing data key. Status: {response.status_code}")
    return [float(x) for x in res_json["data"][0]["embedding"]]

def ingest_data():
    """Production Ingestion Pipeline (OpenRouter 1536-dim + BM25)."""
    json_path = os.path.join(ROOT_DIR, "data", "knowledge_base", "*.json")
    files = glob.glob(json_path)
    
    all_corpus_texts = []
    all_metadata = []
    
    index = pc.Index(INDEX_NAME)
    print("Clearing Pinecone (1536 dims)...")
    try:
        index.delete(delete_all=True)
    except: pass

    for file_path in files:
        file_name = os.path.basename(file_path)
        print(f"Processing {file_name}...")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            if isinstance(data, list):
                chunks = data
                global_meta = {}
            else:
                chunks = data.get("chunks", [])
                global_meta = data.get("metadata", {})
            
            vectors = []
            for i, chunk in enumerate(chunks):
                content = chunk.get("text") or chunk.get("content")
                if not content: continue
                
                section = chunk.get('section', 'General')
                context_summary = chunk.get('context', '')
                possible_questions = "\n".join(chunk.get('possible_questions', []))

                # Contextual Retrieval (Situational Prepending)
                # This ensures the embedding knows exactly WHERE this chunk belongs in the college
                institution = global_meta.get("institution", "MSAJCE")
                dept = global_meta.get("department", "General")
                title = global_meta.get("page_title", file_name)
                
                situational_context = (
                    f"This information is from the {institution} institution, "
                    f"specifically the {dept} department's document titled '{title}'. "
                    f"Section: {section}."
                )

                # Super-Chunk 3.0: High-Precision Contextual Embedding
                super_chunk_text = (
                    f"{situational_context}\n\n"
                    f"SUMMARY: {context_summary}\n"
                    f"QUESTIONS: {possible_questions}\n"
                    f"CONTENT: {content}"
                )
                
                embedding = get_embedding(super_chunk_text)
                
                # Dynamic Entity Flattening for EXACT matching
                entities_raw = chunk.get("entities", {})
                flattened_entities = {}
                for k, v in entities_raw.items():
                    key = f"entity_{k}"
                    if isinstance(v, list):
                        flattened_entities[key] = ", ".join(map(str, v))
                    else:
                        flattened_entities[key] = str(v)

                # Final Enterprise Metadata Schema
                metadata = {
                    "chunk_id": chunk.get("chunk_id", f"{file_name}_{i}"),
                    "institution": institution,
                    "page_title": title,
                    "department": dept,
                    "source_pdf": global_meta.get("source_pdf", file_name),
                    "section": section,
                    "text": content,
                    "chunk_type": chunk.get("chunk_type", "paragraph"),
                    "priority": chunk.get("priority", "medium"),
                    "academic_year": global_meta.get("academic_year", "2025-26"),
                    "version": global_meta.get("version", "3.0"),
                    "is_active": True,
                    "pdf_page_number": chunk.get("pdf_page_number", 0),
                    "last_updated": time.strftime("%Y-%m-%d"),
                    **flattened_entities
                }
                
                vectors.append({"id": metadata["chunk_id"], "values": embedding, "metadata": metadata})
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
    print(f"Enterprise Ingestion Complete (BM25 + OpenRouter 1536-dim)")

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
