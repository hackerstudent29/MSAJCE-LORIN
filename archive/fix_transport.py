import os
import json
import asyncio
import time
import requests
import re
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

# Config
PDF_PATH = "RAG Essentials/rag pdfs/page_04_transport.pdf"
JSON_PATH = "RAG Essentials/rag jsons/page_04_transport.json"
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
VERCEL_AI_KEY = os.getenv("VERCEL_AI_KEY_5")
VERCEL_GATEWAY = "https://ai-gateway.vercel.sh/v1"

parser = LlamaParse(api_key=LLAMA_CLOUD_API_KEY, result_type="text")

async def main():
    print(f"Parsing {PDF_PATH} with FULL TEXT mode...")
    docs = await parser.aload_data(PDF_PATH)
    full_text = "\n\n".join([doc.text for doc in docs])
    
    print(f"Extracted {len(full_text)} characters. Structuring into high-fidelity chunks...")
    
    # We will use a very large prompt to ensure NO route is missed.
    prompt = f"""
    Convert this MSAJCE Transport Schedule into a structured RAG JSON.
    EXTRACT EVERY SINGLE BUS ROUTE (AR 1 to AR 10, R 22, and any Nursing routes).
    For each route, list ALL stops/boarding points.
    
    SCHEMA:
    {{
      "metadata": {{ "institution": "MSAJCE", "page_title": "Transport Schedule" }},
      "chunks": [
        {{
          "chunk_id": "transport_AR5",
          "section": "Bus Route AR 5",
          "text": "Full text including stops like Velachery...",
          "keywords": ["AR5", "Velachery", "MMDA"]
        }}
      ]
    }}
    
    TEXT:
    {full_text}
    """
    
    headers = {"Authorization": f"Bearer {VERCEL_AI_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-4o-mini", # Using mini for speed and cost
        "messages": [{"role": "user", "content": prompt + "\n\nReturn ONLY JSON."}]
    }
    
    resp = requests.post(f"{VERCEL_GATEWAY}/chat/completions", headers=headers, json=data)
    json_content = resp.json()["choices"][0]["message"]["content"]
    
    if "```json" in json_content:
        json_content = json_content.split("```json")[1].split("```")[0].strip()
    
    with open(JSON_PATH, "w", encoding='utf-8') as f:
        f.write(json_content)
    print(f"SUCCESS: Saved {JSON_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
