from pinecone import Pinecone
import os, httpx, json
from dotenv import load_dotenv
load_dotenv()

# Use a working key with dimensions=1024
key = os.getenv('VERCEL_AI_KEY_5')
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
r = httpx.post('https://ai-gateway.vercel.sh/v1/embeddings', headers=headers, 
    json={'model': 'openai/text-embedding-3-small', 'input': 'who is babu charles', 'dimensions': 1024}, timeout=10)
emb = r.json()['data'][0]['embedding']
print(f'Embedding dim: {len(emb)}')

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
idx = pc.Index('msajce-v2')
stats = idx.describe_index_stats()
print(f'Index dim: {stats.dimension}')
print(f'Match: {len(emb) == stats.dimension}')

res = idx.query(vector=[float(x) for x in emb], top_k=5, include_metadata=True)
matches = res['matches']
print(f'Results: {len(matches)}')
for m in matches:
    txt = m['metadata'].get('text', '')[:150]
    sid = m['id']
    sc = m['score']
    print(f'  {sid}: score={sc:.4f} | {txt}')
