import os
import json
import asyncio
import nest_asyncio
from llama_parse import LlamaParse
from llama_index.core import SimpleDirectoryReader
from dotenv import load_dotenv

# Allow nested asyncio loops for notebooks/scripts
nest_asyncio.apply()
load_dotenv()

class UnifiedIngestor:
    def __init__(self, pdf_dir, json_dir, output_file):
        self.pdf_dir = pdf_dir
        self.json_dir = json_dir
        self.output_file = output_file
        self.parser = LlamaParse(
            api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
            result_type="markdown",  # RAG supporting format
            verbose=True
        )
        self.unified_data = []

    async def parse_pdf(self, file_path):
        """Parses PDF using LlamaParse."""
        print(f"Parsing PDF: {os.path.basename(file_path)}...")
        documents = await self.parser.aload_data(file_path)
        return "\n\n".join([doc.text for doc in documents])

    def load_json(self, file_path):
        """Loads JSON data."""
        if not os.path.exists(file_path):
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def is_duplicate(self, text, existing_chunks):
        """Checks if text already exists in chunks (simple character-level check)."""
        # Normalize text for better comparison
        norm_text = "".join(text.split()).lower()
        for chunk in existing_chunks:
            chunk_norm = "".join(chunk["text"].split()).lower()
            if norm_text in chunk_norm or chunk_norm in norm_text:
                return True
        return False

    async def process_all(self):
        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.endswith(".pdf")]
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(self.pdf_dir, pdf_file)
            json_file = pdf_file.replace(".pdf", ".json")
            json_path = os.path.join(self.json_dir, json_file)
            
            # 1. Parse PDF
            pdf_text = await self.parse_pdf(pdf_path)
            
            # 2. Load JSON
            json_data = self.load_json(json_path)
            
            file_chunks = []
            
            if json_data:
                print(f"Found matching JSON for {pdf_file}. Merging...")
                # Use JSON chunks as base
                for chunk in json_data.get("chunks", []):
                    # Add source file info
                    chunk["metadata"] = json_data.get("metadata", {})
                    chunk["source_file"] = pdf_file
                    file_chunks.append(chunk)
                
                # Check if PDF has unique data not in JSON
                # We do a rough check by splitting PDF text into paragraphs
                paragraphs = [p.strip() for p in pdf_text.split("\n\n") if len(p.strip()) > 100]
                for i, p in enumerate(paragraphs):
                    if not self.is_duplicate(p, file_chunks):
                        print(f"Found new content in PDF {pdf_file} (Para {i})")
                        file_chunks.append({
                            "chunk_id": f"{pdf_file}_new_{i}",
                            "text": p,
                            "section": "Extracted from PDF",
                            "source_file": pdf_file,
                            "metadata": {"type": "pdf_extraction"}
                        })
            else:
                print(f"No matching JSON for {pdf_file}. Creating new chunks from PDF...")
                # Just chunk the PDF text
                paragraphs = [p.strip() for p in pdf_text.split("\n\n") if len(p.strip()) > 50]
                for i, p in enumerate(paragraphs):
                    file_chunks.append({
                        "chunk_id": f"{pdf_file}_chunk_{i}",
                        "text": p,
                        "section": "PDF Data",
                        "source_file": pdf_file,
                        "metadata": {"type": "standalone_pdf"}
                    })
            
            self.unified_data.extend(file_chunks)

        # 3. Add JSON files that have NO matching PDF
        json_files = [f for f in os.listdir(self.json_dir) if f.endswith(".json")]
        for j_file in json_files:
            p_file = j_file.replace(".json", ".pdf")
            if p_file not in pdf_files:
                print(f"Adding standalone JSON: {j_file}...")
                j_path = os.path.join(self.json_dir, j_file)
                j_data = self.load_json(j_path)
                if j_data:
                    for chunk in j_data.get("chunks", []):
                        chunk["metadata"] = j_data.get("metadata", {})
                        chunk["source_file"] = j_file
                        self.unified_data.append(chunk)

        # Save final unified data
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(self.unified_data, f, indent=2)
        print(f"Unified ingestion complete. Total Chunks: {len(self.unified_data)}. Saved to {self.output_file}")

if __name__ == "__main__":
    PDF_DIR = r"d:\.gemini\claude RAG\data\RAG Essentials\rag pdfs"
    JSON_DIR = r"d:\.gemini\claude RAG\data\RAG Essentials\rag jsons"
    OUTPUT_FILE = r"d:\.gemini\claude RAG\data\unified_chunks.json"
    
    ingestor = UnifiedIngestor(PDF_DIR, JSON_DIR, OUTPUT_FILE)
    asyncio.run(ingestor.process_all())
