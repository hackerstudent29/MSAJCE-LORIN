import os
import json
import time
import hashlib
import re
import httpx
import bm25s
import Stemmer
import cohere
import logging
import asyncio
from pinecone import Pinecone
from upstash_redis.asyncio import Redis
from dotenv import load_dotenv
from langsmith import traceable
from langfuse import Langfuse

load_dotenv()
logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self):
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index("quickstart")
        self.co = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
        self.redis = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
        self.stemmer = Stemmer.Stemmer("english")
        
        # Self-Healing BM25 Index
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        index_dir = os.path.join(base_dir, "data", "bm25_index")
        chunks_path = os.path.join(base_dir, "data", "unified_chunks.json")
        
        if os.path.exists(index_dir) and os.path.exists(os.path.join(index_dir, "params.index.json")):
            try:
                self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
                print("Lorin Engine: Loaded BM25 index.")
            except Exception as e:
                print(f"Lorin Engine: Load failed: {e}")
                if os.getenv("VERCEL"):
                    print("Lorin Engine: On Vercel, cannot rebuild. Fallback to vector search only.")
                    self.bm25 = None
                else:
                    self._rebuild_bm25(chunks_path, index_dir)
        elif not os.getenv("VERCEL"):
            print("Lorin Engine: Index missing, rebuilding...")
            self._rebuild_bm25(chunks_path, index_dir)
        else:
            print("Lorin Engine: Index missing on Vercel. Fallback to vector only.")
            self.bm25 = None

        self.vercel_gateway_url = "https://ai-gateway.vercel.sh/v1"
        self.openrouter_embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.generation_model = "openai/gpt-4o-mini"
        self.embedding_model = "openai/text-embedding-3-small"
        
        self.langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_BASE_URL")
        )

    def _rebuild_bm25(self, chunks_path, index_dir):
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        corpus = [c['text'] for c in chunks]
        tokens = bm25s.tokenize(corpus, stemmer=self.stemmer)
        self.bm25 = bm25s.BM25(corpus=chunks)
        self.bm25.index(tokens)
        os.makedirs(index_dir, exist_ok=True)
        self.bm25.save(index_dir, corpus=chunks)
        print(f"Lorin Engine: Successfully rebuilt BM25 index with {len(chunks)} chunks.")

    async def _safe_vercel_request(self, data, label="Request", span=None):
        gateway_key = os.getenv('VERCEL_AI_KEY_6') or os.getenv('VERCEL_AI_KEY_5') or os.getenv('AI_GATEWAY_API_KEY')
        if not gateway_key:
            for key, value in os.environ.items():
                if value.startswith("vck_"):
                    gateway_key = value
                    break
        if not gateway_key: return "Error: No AI Key found."
            
        headers = {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0)
                if resp.status_code == 200:
                    res = resp.json()
                    content = res["choices"][0]["message"]["content"]
                    if span: span.event(name=f"LLM {label}", input=data, output=content)
                    return content
                return f"Error {resp.status_code}: {resp.text}"
        except Exception as e: return str(e)

    def _safe_json_parse(self, text):
        try: return json.loads(text.strip())
        except:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None

    @traceable(name="Adaptive Retrieval")
    async def get_context(self, query, trace):
        span = trace.span(name="Retrieval", input={"query": query})
        async with httpx.AsyncClient() as client:
            e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": self.embedding_model, "input": query}, timeout=30.0)
            query_embedding = e_res.json()["data"][0]["embedding"]
        
        pinecone_hits = [m['metadata'] for m in self.index.query(vector=query_embedding, top_k=10, include_metadata=True)['matches']]
        
        bm25_hits = []
        if self.bm25:
            try:
                tokens = bm25s.tokenize(query, stemmer=self.stemmer)
                chunks, _ = self.bm25.retrieve(tokens, k=15)
                bm25_hits = chunks[0].tolist()
            except: pass
        
        combined = []; seen = set()
        for c in pinecone_hits + bm25_hits:
            if c['chunk_id'] not in seen:
                combined.append(c); seen.add(c['chunk_id'])
        
        if not combined: return []
        
        texts = [c['text'] for c in combined]
        loop = asyncio.get_event_loop()
        rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=8))
        
        results = [combined[r.index] for r in rerank.results]
        span.end(output={"results": len(results)})
        return results

    async def query(self, user_query, history=None):
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        
        # 1. Intent & Refinement
        span = trace.span(name="Pre-Processor")
        data = {
            "model": self.generation_model,
            "messages": [{"role": "system", "content": "Classify intent and rewrite for search. Return JSON: {category, search_query, direct_response}"}, {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}],
            "max_tokens": 200
        }
        res = await self._safe_vercel_request(data, label="Pre-Processor", span=span)
        p = self._safe_json_parse(res)
        
        search_query = p.get("search_query", user_query) if p else user_query
        if p and p.get("category") == "GREETING" and p.get("direct_response"):
            return p.get("direct_response")

        # 2. Retrieval
        context_chunks = await self.get_context(search_query, trace)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])

        # 3. Generation
        gen_span = trace.span(name="Generation")
        sys_prompt = "You are Lorin, MSAJCE college buddy. Answer based ONLY on context. Use bullet lists for multiple items. End with a follow-up question. Return JSON: {answer}"
        data_gen = {
            "model": self.generation_model,
            "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"Context: {context_text}\nQuery: {user_query}"}],
            "max_tokens": 800
        }
        res_gen = await self._safe_vercel_request(data_gen, label="Generator", span=gen_span)
        p_gen = self._safe_json_parse(res_gen)
        
        final_answer = p_gen.get("answer", res_gen) if p_gen else res_gen
        trace.update(output=final_answer)
        return final_answer
