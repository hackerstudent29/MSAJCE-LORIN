import json
import glob
import os

kb_path = "data/knowledge_base/*.json"
files = glob.glob(kb_path)
total_chunks = 0

print("Dataset Chunk Audit:")
print("-" * 30)
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        data = json.load(file)
        if isinstance(data, list):
            count = len(data)
        else:
            count = len(data.get("chunks", []))
        total_chunks += count
        print(f"{os.path.basename(f):<30} : {count} chunks")

print("-" * 30)
print(f"TOTAL SYSTEM CHUNKS           : {total_chunks}")
