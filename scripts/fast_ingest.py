import os
import json

def fast_ingest():
    json_dir = r"d:\.gemini\claude RAG\data\RAG Essentials\rag jsons"
    output_file = r"d:\.gemini\claude RAG\data\unified_chunks.json"
    
    all_chunks = []
    
    for filename in os.listdir(json_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(json_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    # Some files might be lists directly, others might have {"chunks": [...]}
                    if isinstance(data, dict) and "chunks" in data:
                        chunks = data["chunks"]
                        metadata = data.get("metadata", {})
                        for chunk in chunks:
                            # ensure chunk_id exists
                            if "chunk_id" not in chunk and "id" in chunk:
                                chunk["chunk_id"] = chunk["id"]
                                
                            if "text" not in chunk and "content" in chunk:
                                chunk["text"] = chunk["content"]
                            
                            if "metadata" not in chunk:
                                chunk["metadata"] = metadata
                            
                            chunk["source_file"] = filename
                            all_chunks.append(chunk)
                    elif isinstance(data, list):
                        for chunk in data:
                            if "chunk_id" not in chunk and "id" in chunk:
                                chunk["chunk_id"] = chunk["id"]
                            chunk["source_file"] = filename
                            all_chunks.append(chunk)
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2)
        
    print(f"Successfully combined {len(all_chunks)} chunks into {output_file}")

if __name__ == "__main__":
    fast_ingest()
