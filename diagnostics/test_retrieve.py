import os
import requests
from pinecone import Pinecone
from dotenv import load_dotenv
import bm25s
import Stemmer
import cohere

load_dotenv()

def test():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("quickstart")
    co = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
    stemmer = Stemmer.Stemmer("english")
    bm25 = bm25s.BM25.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bm25_index"), load_corpus=True)
    
    query = "Dr. E. Dhiravidamani"
    print(f"=== Testing Query: '{query}' ===")
    
    # 1. Embed & Pinecone
    headers = {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}", "Content-Type": "application/json"}
    data = {"model": "openai/text-embedding-3-small", "input": query}
    resp = requests.post("https://openrouter.ai/api/v1/embeddings", headers=headers, json=data)
    
    pinecone_chunks = []
    if resp.status_code == 200:
        q_vector = resp.json()["data"][0]["embedding"]
        matches = index.query(vector=q_vector, top_k=15, include_metadata=True)['matches']
        pinecone_chunks = [m['metadata'] for m in matches]
        
    # 2. BM25
    bm25_hits = []
    try:
        query_tokens = bm25s.tokenize(query, stemmer=stemmer)
        bm25_chunks, bm25_scores = bm25.retrieve(query_tokens, k=15)
        bm25_hits = bm25_chunks[0].tolist()
    except Exception as e:
        pass
        
    combined = []
    seen = set()
    for c in pinecone_chunks + bm25_hits:
        if c['chunk_id'] not in seen:
            combined.append(c); seen.add(c['chunk_id'])
            
    print(f"Total combined chunks before rerank: {len(combined)}")
    
    if combined:
        texts = [c['text'] for c in combined]
        rerank = co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=10)
        print("Cohere Rerank results:")
        for r in rerank.results:
            print(f" - Score: {r.relevance_score}, Text: {texts[r.index][:150]}...")

if __name__ == "__main__":
    test()
