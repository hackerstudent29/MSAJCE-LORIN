import os
import re
import json
import requests
from llama_parse import LlamaParse
from dotenv import load_dotenv

load_dotenv()

def sanitize_content(text):
    """
    Uses GPT-4o-mini to intelligently scrub headers, footers, nav-links, and FAQs.
    """
    prompt = (
        "You are a document sanitization expert. Clean the following text to make it perfect for a RAG system.\n\n"
        "STRICT INSTRUCTIONS:\n"
        "1. REMOVE all headers, footers, and page numbers.\n"
        "2. REMOVE all navigation bar links (Home, Contact Us, Login, etc.).\n"
        "3. REMOVE all social media links and repetitive 'Click here' buttons.\n"
        "4. REMOVE all FAQ (Frequently Asked Questions) sections.\n"
        "5. REMOVE any 'Read More' or 'Chunk' boilerplate.\n"
        "6. KEEP all institutional facts, contact details (if official), and core data.\n\n"
        "Return the CLEANED text only.\n\n"
        f"TEXT TO CLEAN:\n{text}"
    )
    
    headers = {
        "Authorization": f"Bearer {os.getenv('VERCEL_AI_KEY_5')}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000
    }
    
    try:
        resp = requests.post("https://ai-gateway.vercel.sh/v1/chat/completions", headers=headers, json=data)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Sanitization error: {e}")
    return text

def main():
    parser = LlamaParse(result_type="markdown")
    input_dir = "data/pdfs"
    output_dir = "data/sanitized_docs"
    os.makedirs(output_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.endswith(".pdf")]
    print(f"Found {len(files)} PDFs. Starting sanitization...")

    for file in files:
        print(f"Processing {file}...")
        input_path = os.path.join(input_dir, file)
        
        # 1. Parse PDF to Markdown
        docs = parser.load_data(input_path)
        raw_text = "\n\n".join([doc.text for doc in docs])
        
        # 2. AI Sanitize
        cleaned_text = sanitize_content(raw_text)
        
        # 3. Save as Markdown (Better for RAG)
        output_filename = file.replace(".pdf", ".md")
        with open(os.path.join(output_dir, output_filename), "w", encoding="utf-8") as f:
            f.write(cleaned_text)
            
        print(f"  [DONE] Sanitized version saved to {output_filename}")

if __name__ == "__main__":
    main()
