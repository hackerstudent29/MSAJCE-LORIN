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

# ── Master Query Classifiers (Master Rule Section 5B) ────────────────────────
LIST_SIGNALS = [
    "list", "all", "who are", "names of", "how many", "give me all",
    "show all", "all students", "all recipients", "everyone", "each",
    "complete list", "full list", "tell me all", "what are all"
]

PERSON_SIGNALS = [
    "who is", "tell me about", "who heads", "who runs", "principal",
    "hod", "head of", "professor", "faculty", "staff"
]

STAT_SIGNALS = [
    "how many", "percentage", "rank", "ranking", "score", "number of",
    "total", "count", "average", "package", "lpa", "placed"
]

def classify_query(query: str) -> str:
    q = query.lower()
    if any(s in q for s in LIST_SIGNALS):   return "list"
    if any(s in q for s in PERSON_SIGNALS): return "person"
    if any(s in q for s in STAT_SIGNALS):   return "stat"
    return "fact"

class RAGEngine:
    def __init__(self):
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            index_name = os.getenv("PINECONE_INDEX_NAME", "raglorin")
            self.pc = Pinecone(api_key=pc_key)
            self.index = self.pc.Index(index_name)
        except: self.index = None

        try:
            self.co = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
        except: self.co = None

        try:
            self.redis = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
        except: self.redis = None

        self.stemmer = Stemmer.Stemmer("english")
        
        # Path detection
        cwd = os.getcwd()
        base_dir = next((root for root in [cwd, os.path.dirname(cwd), os.path.dirname(os.path.abspath(__file__))] 
                        if os.path.exists(os.path.join(root, "data", "unified_master_chunks.json"))), None)
        
        if base_dir:
            index_dir = os.path.join(base_dir, "data", "bm25_index")
            if os.path.exists(os.path.join(index_dir, "params.index.json")):
                self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
            else: self.bm25 = None
        else: self.bm25 = None

        self.vercel_gateway_url = "https://ai-gateway.vercel.sh/v1"
        self.openrouter_embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.generation_model = "google/gemini-2.0-flash-001"
        self.embedding_model = "openai/text-embedding-3-small"
        self.langfuse = Langfuse()

    def _safe_json_parse(self, text):
        try: return json.loads(text.strip())
        except:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None

    @traceable(name="Hybrid Retrieval")
    async def get_context(self, query, trace):
        q_type = classify_query(query)
        
        async def fetch_pinecone():
            if not self.index: return []
            try:
                top_k = 15 if q_type in ["person", "stat"] else 20
                async with httpx.AsyncClient() as client:
                    e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, 
                                             json={"model": self.embedding_model, "input": query}, timeout=10.0)
                    emb = e_res.json()["data"][0]["embedding"]
                    p_res = self.index.query(vector=emb, top_k=top_k, include_metadata=True)
                    return [{"text": m["metadata"]["text"], "score": m["score"], "id": m["id"], "metadata": m["metadata"]} for m in p_res["matches"]]
            except: return []

        async def fetch_bm25():
            if not self.bm25: return []
            try:
                k = 15 if q_type == "list" else 10
                tokens = bm25s.tokenize(query, stemmer=self.stemmer)
                chunks, scores = self.bm25.retrieve(tokens, k=k)
                return [{"text": c["text"], "score": float(s), "id": c["chunk_id"], "metadata": c["metadata"]} for c, s in zip(chunks[0], scores[0])]
            except: return []

        p_hits, b_hits = await asyncio.gather(fetch_pinecone(), fetch_bm25())
        w = {"list": (0.4, 0.6), "person": (0.6, 0.4), "stat": (0.7, 0.3), "fact": (0.7, 0.3)}[q_type]
        
        combined = {}; seen = set()
        for h in p_hits:
            h["f_score"] = h["score"] * w[0]
            combined[h["id"]] = h
        for h in b_hits:
            if h["id"] in combined: combined[h["id"]]["f_score"] += h["score"] * w[1]
            else: h["f_score"] = h["score"] * w[1]; combined[h["id"]] = h
        
        results = sorted(combined.values(), key=lambda x: x["f_score"], reverse=True)
        if not results: return []

        texts = [r["text"] for r in results]
        try:
            loop = asyncio.get_event_loop()
            top_n = 8 if q_type in ["person", "stat"] else 10
            rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=top_n))
            reranked = [results[r.index] for r in rerank.results]
        except: reranked = results[:10]

        if q_type == "list":
            vips = [r for r in results if r["metadata"].get("chunk_type") == "group_list"]
            non_vips = [r for r in reranked if r["metadata"].get("chunk_type") != "group_list"]
            return (vips + non_vips)[:10]
        
        if q_type == "person":
            profs = [r for r in reranked if "profile" in r["metadata"].get("source_file", "").lower() or "faculty" in r["metadata"].get("section", "").lower()]
            others = [r for r in reranked if r not in profs]
            return (profs + others)[:8]

        return reranked[:10]

    async def query_stream(self, user_query, history=None):
        start_time = time.time()
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        
        # 1. Intent & Refinement (Restored)
        span = trace.span(name="Pre-Processor")
        data_pre = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": """Classify intent and rewrite for search. 
Return JSON: {category, search_query, direct_response, is_count_only}

CATEGORIES: 
- DEVELOPER: ONLY for Ramanathan S or Ram.
- GREETING: Hello, hi.
- INSTITUTIONAL: Default for all others.

STRICT RULES:
1. IDENTITY: Srinivasan/Principal = INSTITUTIONAL. Never give DEVELOPER bio for them.
2. DEVELOPER (Ramanathan S): 
   - Direct intro for 'who is ram'.
   - Search query for follow-ups.
3. FOLLOW-UPS: Always prompt for more about Zenify, Zenpay, or Lorin RAG.

BIO: "**Ramanathan S (Ram)** is the Lead AI Developer and System Architect at MSAJCE. 2nd-year B.Tech IT student.
• [LinkedIn](https://linkedin.com/in/ramanathan-s)
• [Portfolio](https://ram-ai-portfolio.vercel.app)
• [GitHub](https://github.com/hackerstudent29)"
"""}, 
                {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
            ]
        }
        
        pre_res = ""
        async for chunk in self._safe_vercel_request(data_pre):
            pre_res += chunk
        p = self._safe_json_parse(pre_res)
        
        if p and p.get("direct_response"):
            yield p.get("direct_response"); return

        # 2. Context Retrieval
        search_query = p.get("search_query", user_query) if p else user_query
        context_chunks = await self.get_context(search_query, trace)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])

        # 3. Generation (Restored Rich Prompt)
        is_count_only = p.get("is_count_only", False) if p else False
        system_prompt = f"""You are Lorin, the institutional assistant for MSAJCE. 
Tone: casual, friendly, helpful.

STRICT RULES:
1. LISTS: List EVERY unique name found. Never summarize.
2. RAMANATHAN: If query is about the dev, use the profile. ALWAYS ask if they want to know about Zenify or Zenpay.
3. FOLLOW-UPS: At the end of EVERY answer, ask a short, relevant follow-up question.
4. {"STRICT RULE: The user is asking for a COUNT. PROVIDE SUMMARY ONLY." if is_count_only else ""}

CONTEXT: {context_text}
History: {history if history else "None"}"""

        data_gen = {"model": self.generation_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Query: {user_query}"}], "max_tokens": 1000}
        
        full_answer = ""
        async for chunk in self._safe_vercel_request(data_gen, stream=True):
            full_answer += chunk
            yield chunk
            
        trace.update(output=full_answer)

    async def _safe_vercel_request(self, data, stream=False):
        gateway_key = (os.getenv('VERCEL_AI_KEY_6') or os.getenv('VERCEL_AI_KEY_5') or os.getenv('AI_GATEWAY_API_KEY'))
        if not gateway_key:
            for key, value in os.environ.items():
                if value and (value.startswith("vck_") or value.startswith("vcp_")):
                    gateway_key = value; break
        
        if not gateway_key: yield "Error: No API Key"; return
        if stream: data["stream"] = True
        headers = {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            if not stream:
                resp = await client.post(f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0)
                yield resp.json()["choices"][0]["message"]["content"]
            else:
                async with client.stream("POST", f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            if line == "data: [DONE]": break
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk["choices"][0]["delta"].get("content", "")
                                if delta: yield delta
                            except: continue
