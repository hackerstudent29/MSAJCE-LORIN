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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
PDF_DIR = os.path.join(ROOT_DIR, "data", "pdfs")
JSON_DIR = os.path.join(ROOT_DIR, "data", "jsons")
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")
VERCEL_AI_KEY = os.getenv("VERCEL_AI_KEY_5")
VERCEL_GATEWAY = "https://ai-gateway.vercel.sh/v1"

# Initialize Parser
parser = LlamaParse(
    api_key=LLAMA_CLOUD_API_KEY,
    result_type="markdown",
    num_workers=4,
    verbose=True,
    language="en",
)

def safe_vercel_json(prompt, label="Structuring", retries=3):
    headers = {"Authorization": f"Bearer {VERCEL_AI_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No other text."}]
    }
    
    for attempt in range(retries):
        try:
            resp = requests.post(f"{VERCEL_GATEWAY}/chat/completions", headers=headers, json=data, timeout=60)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                # Extract JSON if wrapped in markdown code blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return content.strip()
            
            if resp.status_code == 429:
                time.sleep(10)
                continue
            
            print(f"    [Error {resp.status_code}] {resp.text[:100]}")
        except Exception as e:
            print(f"    [Exception] {str(e)}")
            time.sleep(5)
    return None

async def main():
    if not os.path.exists(JSON_DIR): os.makedirs(JSON_DIR)
    
    for pdf_file in os.listdir(PDF_DIR):
        if not pdf_file.endswith(".pdf"): continue
        
        print(f"\n--- PROCESSING: {pdf_file} ---")
        file_path = os.path.join(PDF_DIR, pdf_file)
        
        try:
            documents = await parser.aload_data(file_path)
            markdown_text = "\n\n".join([doc.text for doc in documents])
            
            prompt = f"""Convert this Markdown into structured RAG JSON schema. Metadata title: {pdf_file}.
            SCHEMA: {{ "metadata": {{...}}, "chunks": [ {{ "chunk_id": "...", "section": "...", "text": "...", "possible_questions": [], "entities": {{ "persons": [], "locations": [] }}, "keywords": [] }} ] }}
            
            TEXT:
            {markdown_text[:8000]}"""
            
            json_content = safe_vercel_json(prompt)
            
            if json_content:
                # Basic validation
                try:
                    json.loads(json_content)
                    output_name = pdf_file.replace(".pdf", ".json")
                    output_path = os.path.join(JSON_DIR, output_name)
                    with open(output_path, "w", encoding='utf-8') as f:
                        f.write(json_content)
                    print(f"  SUCCESS: Saved {output_name}")
                except:
                    print(f"  FAILED: Invalid JSON returned for {pdf_file}")
            else:
                print(f"  FAILED to get content for {pdf_file}")
                
        except Exception as e:
            print(f"  FAILED to parse {pdf_file}: {str(e)}")
        
        await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
