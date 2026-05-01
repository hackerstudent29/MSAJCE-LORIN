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
from datetime import datetime
from pinecone import Pinecone
from upstash_redis.asyncio import Redis
from dotenv import load_dotenv
from langsmith import traceable
from langfuse import Langfuse

load_dotenv()
logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self):
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            index_name = os.getenv("PINECONE_INDEX_NAME", "raglorin")
            if not pc_key: raise ValueError("Missing PINECONE_API_KEY")
            self.pc = Pinecone(api_key=pc_key)
            self.index = self.pc.Index(index_name)
            print(f"Lorin Engine: Connected to Pinecone index: {index_name}")
        except Exception as e:
            print(f"Lorin Engine: Pinecone Init Error: {e}")
            self.index = None

        try:
            co_key = os.getenv("COHERE_API_KEY")
            if not co_key: raise ValueError("Missing COHERE_API_KEY")
            self.co = cohere.ClientV2(co_key)
        except Exception as e:
            print(f"Lorin Engine: Cohere Init Error: {e}")
            self.co = None

        try:
            redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
            redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
            if not redis_url or not redis_token: raise ValueError("Missing Upstash Redis credentials")
            self.redis = Redis(url=redis_url, token=redis_token)
        except Exception as e:
            print(f"Lorin Engine: Redis Init Error: {e}")
            self.redis = None

        self.stemmer = Stemmer.Stemmer("english")
        
        # Robust Path Detection for Vercel/Cloud
        cwd = os.getcwd()
        possible_roots = [cwd, os.path.dirname(cwd), os.path.dirname(os.path.abspath(__file__)), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
        
        base_dir = None
        for root in possible_roots:
            test_path = os.path.join(root, "data", "unified_master_chunks.json")
            if os.path.exists(test_path):
                base_dir = root
                break
        
        if not base_dir:
            print(f"Lorin Engine: WARNING! Could not find 'data' folder. Searched: {possible_roots}")
            self.bm25 = None
        else:
            index_dir = os.path.join(base_dir, "data", "bm25_index")
            print(f"Lorin Engine: Knowledge base detected at {base_dir}")
            
            if os.path.exists(index_dir) and os.path.exists(os.path.join(index_dir, "params.index.json")):
                try:
                    self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
                    print(f"Lorin Engine: Loaded BM25 index from {index_dir}")
                except Exception as load_err:
                    print(f"Lorin Engine: BM25 Load Error: {load_err}")
                    self.bm25 = None
            else:
                print(f"Lorin Engine: BM25 index missing or corrupt. Fallback to vector only.")
                self.bm25 = None

        self.vercel_gateway_url = "https://ai-gateway.vercel.sh/v1"
        self.openrouter_embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.generation_model = "google/gemini-2.0-flash-001"
        self.embedding_model = "openai/text-embedding-3-small"
        
        self.langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_BASE_URL")
        )

    def _rebuild_bm25(self, chunks_path, index_dir):
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        # New master chunk structure: list of dicts with 'text'
        corpus = [c['text'] for c in chunks]
        tokens = bm25s.tokenize(corpus, stemmer=self.stemmer)
        
        # Save corpus with metadata
        self.bm25 = bm25s.BM25(corpus=chunks)
        self.bm25.index(tokens)
        os.makedirs(index_dir, exist_ok=True)
        self.bm25.save(index_dir, corpus=chunks)
        print(f"Lorin Engine: Successfully rebuilt BM25 index with {len(chunks)} Diamond Chunks.")

    async def _safe_vercel_request(self, data, label="Request", span=None, stream=False):
        gateway_key = os.getenv('VERCEL_AI_KEY_6') or os.getenv('VERCEL_AI_KEY_5') or os.getenv('AI_GATEWAY_API_KEY')
        if not gateway_key:
            for key, value in os.environ.items():
                if value and (value.startswith("vck_") or value.startswith("vcp_")):
                    gateway_key = value
                    break
        
        if not gateway_key: 
            yield f"Error: No AI Gateway Key found for {label}."
            return

        if stream: data["stream"] = True
            
        headers = {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient() as client:
                if not stream:
                    resp = await client.post(f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0)
                    if resp.status_code == 200:
                        res = resp.json()
                        content = res["choices"][0]["message"]["content"]
                        if span: span.event(name=f"LLM {label}", input=data, output=content)
                        yield content
                    else: yield f"Error {resp.status_code}: {resp.text}"
                else:
                    async with client.stream("POST", f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0) as response:
                        if response.status_code != 200:
                            yield f"Error {response.status_code}"
                            return
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "): continue
                            if line == "data: [DONE]": break
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta: yield delta
                            except: continue
        except Exception as e:
            yield str(e)

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
        async def fetch_pinecone():
            if not self.index: return []
            try:
                async with httpx.AsyncClient() as client:
                    e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": self.embedding_model, "input": query}, timeout=10.0)
                    query_embedding = e_res.json()["data"][0]["embedding"]
                    p_res = self.index.query(vector=query_embedding, top_k=20, include_metadata=True)
                    return [{"text": m["metadata"]["text"], "score": m["score"], "chunk_id": m["id"], "entity": m["metadata"].get("entity", "N/A")} for m in p_res["matches"]]
            except: return []

        async def fetch_bm25():
            if not self.bm25: return []
            try:
                tokens = bm25s.tokenize(query, stemmer=self.stemmer)
                chunks, _ = self.bm25.retrieve(tokens, k=15)
                return chunks[0].tolist()
            except: return []

        p_hits, b_hits = await asyncio.gather(fetch_pinecone(), fetch_bm25())
        combined = []; seen = set()
        for c in p_hits + b_hits:
            cid = c.get('chunk_id') or c.get('id')
            if cid and cid not in seen: combined.append(c); seen.add(cid)
        
        if not combined: return []
        texts = [c['text'] for c in combined]
        if self.co:
            try:
                loop = asyncio.get_event_loop()
                rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=15))
                return [combined[r.index] for r in rerank.results]
            except: pass
        return combined[:20]

    async def query(self, user_query, history=None):
        full_text = ""
        async for chunk in self.query_stream(user_query, history): full_text += chunk
        return full_text

    async def query_stream(self, user_query, history=None):
        start_time = time.time()
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        # 1. Intent & Refinement
        span = trace.span(name="Pre-Processor")
        data = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": """Classify intent and rewrite for search. 
Return JSON: {category, search_query, direct_response, is_count_only}

CATEGORIES: 
- DEVELOPER: ONLY for Ramanathan S or Ram.
- GREETING: Hello, hi.
- INSTITUTIONAL: Default for all other people (Principal, Faculty, Students), departments, etc.

STRICT RULES:
1. IDENTITY CHECK: If the query is about 'Srinivasan', 'Principal', or any faculty name NOT named Ramanathan, it MUST be CATEGORY: INSTITUTIONAL. Never give the DEVELOPER bio for these names.
2. FOR DEVELOPER (Ramanathan S):
   - Only give direct_response for initial intro ('who is ram', 'who made you').
   - For follow-ups ('tell me more', 'skills', 'projects'), set direct_response: null and search_query: 'Ramanathan S projects skills architecture'.
3. INTENT: Set is_count_only: true for 'how many'/'total' queries.
4. TYPO-PROOFING: Correct names.

STANDARD DEVELOPER BIO:
"**Ramanathan S (Ram)** is the Lead AI Developer and System Architect at MSAJCE. He is a 2nd-year B.Tech IT student specializing in AI systems, Fintech architecture, and high-performance RAG engines.
• [LinkedIn](https://linkedin.com/in/ramanathan-s)
• [Portfolio](https://ram-ai-portfolio.vercel.app)

Would you like to know more about his major engineering projects like **Zenify**, **Zenpay**, or the architecture behind **Lorin RAG**?"
"""}, 
                {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
            ],
            "max_tokens": 400
        }
        
        # Collect pre-processor response from generator
        res = ""
        async for chunk in self._safe_vercel_request(data, label="Pre-Processor", span=span):
            res += chunk
            
        p = self._safe_json_parse(res)
        if p and p.get("direct_response"):
            yield p.get("direct_response"); return
            
        search_query = p.get("search_query", user_query) if p else user_query
        context_chunks = await self.get_context(search_query, trace)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])

        gen_span = trace.span(name="Generation")
        is_count_only = p.get("is_count_only", False) if p else False
        system_prompt = f"""You are Lorin, the institutional assistant for MSAJCE. Tone: casual, friendly.

STRICT RULES FOR LISTS:
1. If the user asks for a 'list', 'names', or 'all', you MUST search the context for EVERY UNIQUE NAME and list them one by one. 
2. NEVER summarize a list of people (e.g., don't say 'including X and Y'). List EVERYONE found.
3. REMOVE DUPLICATES: If you see the same name/batch in different sources, only list it once.
4. {"STRICT RULE: The user is asking for a COUNT. PROVIDE SUMMARY ONLY. NO LISTS." if is_count_only else ""}

RULES: Bullet points prefix '• ', vertical layout, closing with follow-up.
CONTEXT: {context_text}
History: {history if history else "None"}"""

        data_gen = {"model": self.generation_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Query: {user_query}"}], "max_tokens": 1000}
        full_answer = ""
        async for chunk in self._safe_vercel_request(data_gen, label="Generator", span=gen_span, stream=True):
            full_answer += chunk
            yield chunk
        trace.update(output=full_answer)
        try:
            log_entry = {"timestamp": datetime.now().isoformat(), "query": user_query, "category": p.get("category", "GENERAL") if p else "ERROR", "latency": int((time.time() - start_time) * 1000), "status": "SUCCESS"}
            await self.redis.lpush("lorin_forensic_logs", json.dumps(log_entry))
        except: pass
