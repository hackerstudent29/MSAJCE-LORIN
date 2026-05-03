import os
import json
import time
import requests
import bm25s
import Stemmer
from pinecone import Pinecone
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# Config
JSON_DIR = r"d:\.gemini\claude RAG\data\RAG Essentials\rag jsons"
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
EMBEDDING_MODEL = "openai/text-embedding-3-small"
INDEX_NAME = "quickstart"
BM25_DIR = r"d:\.gemini\claude RAG\data\bm25_index"

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
    for _ in range(3): # Retry logic
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
    # 1. Initialize Pinecone
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(INDEX_NAME)
    
    # 2. Collect all chunks
    all_chunks = []
    print("Reading JSON files...")
    for filename in os.listdir(JSON_DIR):
        if filename.endswith(".json"):
            path = os.path.join(JSON_DIR, filename)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for chunk in data.get("chunks", []):
                    chunk['filename'] = filename
                    all_chunks.append(chunk)
    
    print(f"Found {len(all_chunks)} chunks to process.")
    
    # 3. Pinecone Ingestion
    print("Ingesting to Pinecone...")
    vectors = []
    bm25_corpus = []
    
    for i, chunk in enumerate(tqdm(all_chunks)):
        content_text = chunk.get('text') or chunk.get('content')
        if not content_text:
            continue
            
        # 1. Table Formatting (NEW: Make tables readable for RAG)
        tables_md = ""
        for table in chunk.get('tables', []):
            title = table.get('table_title', 'Table')
            headers = table.get('headers', [])
            rows = table.get('rows', [])
            if headers:
                tables_md += f"\n\n### {title}\n| " + " | ".join(headers) + " |\n"
                tables_md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in rows:
                    tables_md += "| " + " | ".join([str(cell) for cell in row]) + " |\n"
        
        full_text = content_text + tables_md
        
        context = chunk.get('context', '')
        section = chunk.get('section', '')
        keywords_list = chunk.get('keywords', [])
        keywords_str = ", ".join(keywords_list)
        
        # 2. Advanced Embedding Enrichment (Context + Keywords + Entities + Tables)
        entities_data = chunk.get("entities", {})
        persons = entities_data.get("persons", [])
        
        # Add names to keywords for better lexical retrieval
        names_str = ", ".join(persons)
        enhanced_keywords = keywords_str
        if names_str:
            enhanced_keywords += f", {names_str}"
            
        embed_text = f"SECTION: {section}\nCONTEXT: {context}\nKEYWORDS: {enhanced_keywords}\n\nCONTENT:\n{full_text}"
        
        vector = get_embedding(embed_text)
        if vector:
            metadata = {
                "text": full_text, 
                "section": section,
                "source_url": chunk.get("source_url", ""),
                "filename": filename,
                "chunk_id": chunk['chunk_id'],
                "context": context,
                "entities": json.dumps(entities_data),
                "keywords": enhanced_keywords
            }
            vectors.append({
                "id": f"{filename}_{chunk['chunk_id']}",
                "values": vector,
                "metadata": metadata
            })
            
            # For BM25
            bm25_corpus.append(metadata)
        
        # Upsert in batches of 50
        if len(vectors) >= 50:
            index.upsert(vectors=vectors)
            vectors = []
            time.sleep(0.5) # Avoid rate limits
            
    if vectors:
        index.upsert(vectors=vectors)

    print("Pinecone Ingestion Complete.")

    # 4. Build BM25 Index
    print("Building BM25 Index...")
    stemmer = Stemmer.Stemmer("english")
    
    # Extract text and keywords for lexical indexing
    corpus_texts = [f"{c['text']} {c['keywords']}" for c in bm25_corpus]
    tokens = bm25s.tokenize(corpus_texts, stemmer=stemmer)
    
    bm25 = bm25s.BM25()
    bm25.index(tokens)
    
    # Save BM25 index and corpus
    if not os.path.exists(BM25_DIR):
        os.makedirs(BM25_DIR)
        
    bm25.save(BM25_DIR, corpus=bm25_corpus)
    print(f"BM25 Index saved to {BM25_DIR}")

if __name__ == "__main__":
    process_ingestion()
