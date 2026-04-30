import os
import json
import time
import bm25s
import Stemmer
from pinecone import Pinecone
from dotenv import load_dotenv
import requests

load_dotenv()

class IndexSyncer:
    def __init__(self, chunks_file):
        self.chunks_file = chunks_file
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.pc = Pinecone(api_key=self.pinecone_api_key)
        self.index = self.pc.Index("quickstart") # From core/engine.py
        self.embedding_url = "https://openrouter.ai/api/v1/embeddings"
        self.embedding_model = "openai/text-embedding-3-small"

    def get_embeddings_batch(self, texts):
        """Batch embedding request."""
        headers = {"Authorization": f"Bearer {self.openrouter_api_key}", "Content-Type": "application/json"}
        data = {"model": self.embedding_model, "input": texts}
        response = requests.post(self.embedding_url, headers=headers, json=data)
        if response.status_code != 200:
            print(f"Error embedding: {response.text}")
            return None
        return [item["embedding"] for item in response.json()["data"]]

    def sync_to_pinecone(self, chunks):
        print(f"Syncing {len(chunks)} chunks to Pinecone...")
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            texts = [c["text"] for c in batch]
            vectors = self.get_embeddings_batch(texts)
            
            if not vectors: continue
            
            upserts = []
            for j, chunk in enumerate(batch):
                upserts.append({
                    "id": chunk["chunk_id"],
                    "values": [float(v) for v in vectors[j]],
                    "metadata": {
                        "text": chunk["text"],
                        "chunk_id": chunk["chunk_id"],
                        "section": chunk.get("section", "General"),
                        "source": chunk.get("source_file", "unknown")
                    }
                })
            
            self.index.upsert(vectors=upserts)
            print(f"Upserted batch {i//batch_size + 1}/{(len(chunks)-1)//batch_size + 1}")
            time.sleep(1) # Small delay to be safe

    def sync_to_bm25(self, chunks):
        print("Syncing to BM25 local index...")
        stemmer = Stemmer.Stemmer("english")
        
        # Format for BM25: List of texts
        corpus = [c["text"] for c in chunks]
        
        # Tokenize
        tokens = bm25s.tokenize(corpus, stemmer=stemmer)
        
        # Create and Save
        bm25 = bm25s.BM25(corpus=chunks) # We save the chunk dict as corpus
        bm25.index(tokens)
        
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        save_path = os.path.join(root_dir, "data", "bm25_index")
        
        if not os.path.exists(save_path):
            os.makedirs(save_path)
            
        bm25.save(save_path)
        print(f"BM25 Index saved to {save_path}")

    def run(self):
        with open(self.chunks_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        
        # 1. Pinecone
        self.sync_to_pinecone(chunks)
        
        # 2. BM25
        self.sync_to_bm25(chunks)
        
        print("\nALL INDICES SYNCED SUCCESSFULLY.")

if __name__ == "__main__":
    CHUNKS_FILE = r"d:\.gemini\claude RAG\data\unified_chunks.json"
    syncer = IndexSyncer(CHUNKS_FILE)
    syncer.run()
