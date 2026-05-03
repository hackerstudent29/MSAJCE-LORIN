import os
import json

def fast_merge():
    json_dir = r"d:\.gemini\claude RAG\data\jsons"
    output_file = r"d:\.gemini\claude RAG\data\unified_chunks.json"
    unified_data = []

    print(f"Lorin Brain Builder: Starting Fast Merge from {json_dir}...")

    # Load all JSON files in the directory
    json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
    
    total_files = 0
    for j_file in json_files:
        j_path = os.path.join(json_dir, j_file)
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                j_data = json.load(f)
            
            if j_data and "chunks" in j_data:
                for chunk in j_data["chunks"]:
                    # Attach metadata and source file for retrieval context
                    chunk["metadata"] = j_data.get("metadata", {})
                    chunk["source_file"] = j_file
                    unified_data.append(chunk)
                total_files += 1
                print(f"[SUCCESS] Merged: {j_file} ({len(j_data['chunks'])} chunks)")
        except Exception as e:
            print(f"[ERROR] merging {j_file}: {e}")

    # Save final unified data
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(unified_data, f, indent=2)
    
    print("-" * 50)
    print(f"BUILD COMPLETE: Total Chunks: {len(unified_data)} across {total_files} files.")
    print(f"BRAIN SAVED TO: {output_file}")

if __name__ == "__main__":
    fast_merge()
