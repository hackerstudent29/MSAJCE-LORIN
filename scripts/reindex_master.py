import os
import json
import asyncio
import httpx
from pinecone import Pinecone
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

class MasterReindexer:
    def __init__(self):
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "raglorin")
        self.index = self.pc.Index(self.index_name)
        
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.embedding_model = "openai/text-embedding-3-small"
        self.data_path = os.path.join("data", "unified_master_chunks.json")

    async def get_embeddings(self, texts):
        headers = {"Authorization": f"Bearer {self.openrouter_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.embed_url, headers=headers, json=payload)
            resp_json = response.json()
            if 'data' not in resp_json: return None
            return [item['embedding'] for item in resp_json['data']]

    async def run(self):
        print(f"Starting Master Re-index for index: {self.index_name}")
        with open(self.data_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        print(f"Loaded {len(chunks)} master chunks. Wiping index...")
        self.index.delete(delete_all=True)

        batch_size = 20
        for i in tqdm(range(0, len(chunks), batch_size)):
            batch = chunks[i:i + batch_size]
            # Embed with ENRICHED text (Master Rule 2B Step 3)
            texts = [c.get('embed_text', c['text']) for c in batch]
            
            embeddings = await self.get_embeddings(texts)
            if not embeddings: continue
                
            vectors = []
            for j, chunk in enumerate(batch):
                float_embeddings = [float(v) for v in embeddings[j]]
                # Standard Metadata (Master Rule Section 2B Step 4)
                vectors.append({
                    "id": chunk['chunk_id'],
                    "values": float_embeddings,
                    "metadata": chunk['metadata']
                })
            self.index.upsert(vectors=vectors)
            
        print("MASTER RE-INDEX COMPLETE!")

if __name__ == "__main__":
    reindexer = MasterReindexer()
    asyncio.run(reindexer.run())
