import json
import os
import hashlib
import re

def estimate_tokens(text):
    return int(len(text.split()) * 1.3)

def sanitize_id(text):
    return re.sub(r'[^a-zA-Z0-9_]', '_', text.replace(' ', '_'))[:80]

def get_text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def transform_transport():
    transport_path = r"d:\.gemini\claude RAG\data\knowledge_base\page_04_transport.json"
    master_chunks_path = r"d:\.gemini\claude RAG\data\knowledge_base\unified_master_chunks.json"
    
    if not os.path.exists(transport_path):
        print(f"Error: {transport_path} not found")
        return
    
    with open(transport_path, 'r', encoding='utf-8') as f:
        transport_data = json.load(f)
    
    raw_chunks = transport_data.get("chunks", [])
    source_name = "page_04_transport.json"
    
    new_master_chunks = []
    for chunk in raw_chunks:
        text = chunk.get("content", "").strip()
        if not text: continue
        
        chunk_id = chunk.get("chunk_id") or sanitize_id(f"{source_name}_{chunk.get('section','')[:30]}")
        pq_list = chunk.get("possible_questions", [])
        kw_list = chunk.get("keywords", [])
        embed_text = f"{text} {' '.join(pq_list)} {' '.join(kw_list)}".strip()
        
        new_chunk = {
            "chunk_id": chunk_id,
            "text": text,
            "embed_text": embed_text,
            "metadata": {
                "chunk_id": chunk_id,
                "source_file": source_name,
                "section": chunk.get("section", "General"),
                "text": text,
                "chunk_type": chunk.get("chunk_type", "fact"),
                "keywords": kw_list,
                "token_count": estimate_tokens(text)
            }
        }
        new_master_chunks.append(new_chunk)
    
    # Load existing master chunks
    if os.path.exists(master_chunks_path):
        with open(master_chunks_path, 'r', encoding='utf-8') as f:
            master_chunks = json.load(f)
    else:
        master_chunks = []
    
    # Avoid duplicates by chunk_id
    existing_ids = {c["chunk_id"] for c in master_chunks}
    chunks_to_add = [c for c in new_master_chunks if c["chunk_id"] not in existing_ids]
    
    if not chunks_to_add:
        print("No new transport chunks to add (already exists).")
        return
    
    master_chunks.extend(chunks_to_add)
    
    with open(master_chunks_path, 'w', encoding='utf-8') as f:
        json.dump(master_chunks, f, indent=2, ensure_ascii=False)
    
    print(f"Added {len(chunks_to_add)} transport chunks to {master_chunks_path}")
    return chunks_to_add

if __name__ == "__main__":
    transform_transport()
