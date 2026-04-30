import os
import json
import uuid
import re
import requests
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

def smart_clean_and_chunk(text, source_name):
    """
    Uses GPT-4o-mini to transform raw markdown into a list of ATOMIC JSON chunks.
    Ensures one concept per chunk and zero noise.
    """
    prompt = (
        f"You are a RAG Architect. Transform this raw text from '{source_name}' into a list of PRODUCTION-READY JSON chunks.\n\n"
        "STRICT RULES:\n"
        "1. ATOMICITY: Each JSON object must contain exactly ONE concept or topic. Split them if they are combined.\n"
        "2. CLEANING: Remove all headers, footers, navigation links, and boilerplate.\n"
        "3. FORMAT: Return a JSON LIST of objects: [{'topic': '...', 'text': '...', 'tags': []}].\n"
        "4. NO NOISE: Do not include URLs, social media links, or FAQ fragments.\n\n"
        f"RAW TEXT:\n{text}"
    )
    
    headers = {"Authorization": f"Bearer {os.getenv('VERCEL_AI_KEY_5')}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 3000
    }
    
    try:
        resp = requests.post("https://ai-gateway.vercel.sh/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Extract JSON list from response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
    except Exception as e:
        print(f"Smart chunking error: {e}")
    return []

def main():
    parser = LlamaParse(result_type="markdown")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_dir = os.path.join(base_dir, "data", "pdfs")
    output_dir = os.path.join(base_dir, "data", "production_jsons")
    os.makedirs(output_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.endswith(".pdf")]
    print(f"Starting Smart Atomic Chunking for {len(files)} PDFs...")

    for file in files:
        print(f"Processing {file}...")
        input_path = os.path.join(input_dir, file)
        
        # 1. Parse PDF
        docs = parser.load_data(input_path)
        raw_text = "\n\n".join([doc.text for doc in docs])
        
        # 2. Smart Atomic Chunking
        chunks = smart_clean_and_chunk(raw_text, file)
        
        if not chunks:
            print(f"  [SKIPPED] No valid chunks generated for {file}")
            continue

        # 3. Final Formatting
        final_production_list = []
        for i, chunk in enumerate(chunks):
            final_production_list.append({
                "id": f"{file.replace('.pdf', '')}_{i:03}",
                "text": chunk.get("text", ""),
                "metadata": {
                    "source": file,
                    "topic": chunk.get("topic", "General"),
                    "tags": chunk.get("tags", []),
                    "type": "Institutional Fact"
                }
            })
            
        output_filename = file.replace(".pdf", ".json")
        with open(os.path.join(output_dir, output_filename), "w", encoding="utf-8") as f:
            json.dump(final_production_list, f, indent=2)
            
        print(f"  [DONE] Created {len(final_production_list)} Atomic JSON chunks in {output_filename}")

if __name__ == "__main__":
    main()
