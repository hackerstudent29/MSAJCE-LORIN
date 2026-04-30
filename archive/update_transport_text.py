import json

with open('RAG Essentials/rag jsons/page_04_transport.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for chunk in data['chunks']:
    section = chunk.get("section", "Unknown Route")
    # Prefix the text with the route name to ensure the LLM sees it
    chunk['text'] = f"ROUTE {section}: {chunk['text']}"

with open('RAG Essentials/rag jsons/page_04_transport.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("SUCCESS: Explicit route names added to transport JSON.")
