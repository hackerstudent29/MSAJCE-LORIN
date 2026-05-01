import os
import json
import asyncio
import httpx
from pinecone import Pinecone
from tqdm import tqdm
from dotenv import load_dotenv

# Load local environment variables
load_dotenv()

class MasterReindexer:
    def __init__(self):
        # Pinecone Config
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "raglorin")
        self.index = self.pc.Index(self.index_name)
        
        # OpenRouter Config
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.embedding_model = "openai/text-embedding-3-small"
        
        # Data
        self.data_path = os.path.join("data", "unified_master_chunks.json")

    async def get_embeddings(self, texts):
        """Batch generates embeddings via OpenRouter."""
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.embedding_model,
            "input": texts
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.embed_url, headers=headers, json=payload)
            resp_json = response.json()
            if 'data' not in resp_json:
                print(f"OpenRouter Error: {resp_json}")
                return None
            return [item['embedding'] for item in resp_json['data']]

    async def run(self):
        print(f"Starting Master Re-index for index: {self.index_name}")
        
        # 1. Load Data
        with open(self.data_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"Loaded {len(chunks)} master chunks.")
        
        # 2. Wipe Index
        print("Wiping existing index data...")
        try:
            self.index.delete(delete_all=True)
            print("Index wiped successfully.")
        except Exception as e:
            print(f"Warning during wipe: {e}")

        # 3. Process in Batches
        batch_size = 20
        total_batches = (len(chunks) + batch_size - 1) // batch_size
        
        print(f"Processing {total_batches} batches...")
        
        for i in tqdm(range(0, len(chunks), batch_size)):
            batch = chunks[i:i + batch_size]
            texts = [c['text'] for c in batch]
            
            embeddings = await self.get_embeddings(texts)
            if not embeddings:
                print(f"Skipping batch starting at {i} due to error.")
                continue
                
            vectors = []
            for j, chunk in enumerate(batch):
                # Ensure all values are floats to satisfy Pinecone's strict type requirements
                float_embeddings = [float(v) for v in embeddings[j]]
                
                vectors.append({
                    "id": chunk['chunk_id'],
                    "values": float_embeddings,
                    "metadata": {
                        "text": chunk['text'],
                        "type": chunk.get('metadata', {}).get('type', 'GENERAL'),
                        "sources": ",".join(chunk.get('metadata', {}).get('sources', [])),
                        "entity": chunk.get('entity_name', 'N/A')
                    }
                })
            
            # Upsert
            self.index.upsert(vectors=vectors)
            
        print("MASTER RE-INDEX COMPLETE! Lorin is now smarter than ever.")

if __name__ == "__main__":
    reindexer = MasterReindexer()
    asyncio.run(reindexer.run())
