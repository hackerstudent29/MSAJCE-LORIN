import json
import os

json_dir = "data/jsons"
files = sorted([f for f in os.listdir(json_dir) if f.endswith('.json')])
print(f"Total JSON files found: {len(files)}")

for file in files:
    if file.endswith("_v2.json") or file == "unified_chunks.json":
        print(f"Skipping junk: {file}")
        continue
    
    path = os.path.join(json_dir, file)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            chunks = data.get("chunks", [])
            print(f"Processed {file}: {len(chunks)} chunks")
    except Exception as e:
        print(f"ERROR reading {file}: {e}")
