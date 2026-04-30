import os
import json
import uuid
import re
from dotenv import load_dotenv

load_dotenv()

def split_into_atomic_chunks(text):
    """
    Splits markdown into chunks based on headers. 
    Each header section becomes a single atomic chunk.
    """
    # Split by any level of markdown header
    sections = re.split(r'\n(?=#+ )', text)
    chunks = []
    
    for section in sections:
        if not section.strip():
            continue
            
        # Extract title if exists
        title_match = re.search(r'^#+ (.*)', section)
        title = title_match.group(1) if title_match else "General Info"
        
        # Clean content
        content = section.strip()
        
        chunks.append({
            "chunk_id": str(uuid.uuid4())[:8],
            "title": title,
            "text": content
        })
    return chunks

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_dir = os.path.join(base_dir, "data", "sanitized_docs")
    output_dir = os.path.join(base_dir, "data", "production_jsons")
    os.makedirs(output_dir, exist_ok=True)

    files = [f for f in os.listdir(input_dir) if f.endswith(".md")]
    print(f"Starting atomic chunking for {len(files)} docs...")

    for file in files:
        print(f"Chunking {file}...")
        with open(os.path.join(input_dir, file), "r", encoding="utf-8") as f:
            content = f.read()
            
        atomic_chunks = split_into_atomic_chunks(content)
        
        production_data = []
        for i, chunk in enumerate(atomic_chunks):
            production_data.append({
                "id": f"{file.replace('.md', '')}_{i:03}",
                "text": chunk["text"],
                "metadata": {
                    "source": file.replace(".md", ".pdf"),
                    "topic": chunk["title"],
                    "chunk_index": i,
                    "institution": "MSAJCE",
                    "format": "Atomic Markdown"
                }
            })
            
        # Save as a single JSON file per document containing a list of atomic chunks
        output_filename = file.replace(".md", ".json")
        with open(os.path.join(output_dir, output_filename), "w", encoding="utf-8") as f:
            json.dump(production_data, f, indent=2)
            
        print(f"  [DONE] Created {len(production_data)} atomic chunks in {output_filename}")

if __name__ == "__main__":
    main()
