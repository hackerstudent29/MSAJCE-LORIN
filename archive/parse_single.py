import os
import json
import asyncio
import time
import requests
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
VERCEL_AI_KEY = os.getenv("VERCEL_AI_KEY_5")
VERCEL_GATEWAY = "https://ai-gateway.vercel.sh/v1"

parser = LlamaParse(api_key=LLAMA_CLOUD_API_KEY, result_type="markdown")

async def main():
    file_path = "RAG Essentials/rag pdfs/MSAJCE_Professional_Societies.pdf"
    print(f"Parsing {file_path}...")
    
    docs = await parser.aload_data(file_path)
    markdown_text = "\n\n".join([doc.text for doc in docs])
    print(f"Parsed {len(markdown_text)} chars.")
    
    prompt = f"""Convert this Markdown into structured RAG JSON schema. Metadata title: Professional Societies.
    STRICTLY EXTRACT the Vice President of CSI (Computer Society of India).
    SCHEMA: {{ "metadata": {{...}}, "chunks": [ {{ "chunk_id": "...", "section": "...", "text": "...", "entities": {{ "persons": [] }} }} ] }}
    
    TEXT:
    {markdown_text}"""
    
    headers = {"Authorization": f"Bearer {VERCEL_AI_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt + "\n\nReturn ONLY JSON."}]
    }
    
    resp = requests.post(f"{VERCEL_GATEWAY}/chat/completions", headers=headers, json=data)
    json_content = resp.json()["choices"][0]["message"]["content"]
    
    if "```json" in json_content:
        json_content = json_content.split("```json")[1].split("```")[0].strip()
    
    with open("RAG Essentials/rag jsons/msajce_professional_societies.json", "w", encoding='utf-8') as f:
        f.write(json_content)
    print("SUCCESS: Saved msajce_professional_societies.json")

if __name__ == "__main__":
    asyncio.run(main())
