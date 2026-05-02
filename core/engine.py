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
    "hod", "head of", "professor", "faculty", "staff", "student", 
    "convenor", "office bearer", "coordinator", "member"
]

STAT_SIGNALS = [
    "how many", "percentage", "rank", "ranking", "score", "number of",
    "total", "count", "average", "package", "lpa", "placed"
]

def classify_query(query: str) -> str:
    q = query.lower()
    # Typo-resistant person detection (wo is, ho is, etc.)
    if any(s in q for s in ["who is", "who are", "wo is", "ho is", "tell me about"]):
        return "person"
        
    if any(s in q for s in LIST_SIGNALS):   return "list"
    if any(s in q for s in PERSON_SIGNALS): return "person"
    if any(s in q for s in STAT_SIGNALS):   return "stat"
    
    # Fallback: If it looks like a name (2-3 words capitalized or specific names)
    if any(name in q for name in ["yogesh", "saqlin", "mustaq", "vimal", "ram", "santhosh"]):
        return "person"
        
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
        # Person Boost: BM25 (0.7) for high-precision name matching
        w = {"list": (0.4, 0.6), "person": (0.3, 0.7), "stat": (0.7, 0.3), "fact": (0.7, 0.3)}[q_type]
        
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
            # Prioritize Faculty AND Student Leaders/Office Bearers
            profs = [r for r in reranked if "profile" in r["metadata"].get("source_file", "").lower() or 
                    "faculty" in r["metadata"].get("section", "").lower() or 
                    "office bearers" in r["metadata"].get("section", "").lower() or
                    "convenor" in r["metadata"].get("section", "").lower()]
            others = [r for r in reranked if r not in profs]
            return (profs + others)[:8]

        return reranked[:10]

    def _post_process(self, text: str) -> str:
        """Strict aesthetic hardening (Master Rule Section 3)."""
        # 1. Ban all headers (#)
        text = re.sub(r'^#+.*$', '', text, flags=re.MULTILINE)
        
        # 2. Convert all bullets (* or -) to center dots (•)
        # Handle cases like "* Item" or "- Item"
        text = re.sub(r'^[ \t]*[*+-][ \t]+', '• ', text, flags=re.MULTILINE)
        
        # 3. Strip any remaining asterisks (e.g. bolding/italics)
        text = text.replace('*', '')
        
        # 4. Clean up excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        
        return text

    async def query_stream(self, user_query, history=None):
        start_time = time.time()
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        
        # 1. Intent & Refinement (Restored & Improved Memory)
        span = trace.span(name="Pre-Processor")
        data_pre = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": """Classify intent and rewrite for search. 
Analyze HISTORY to see if this is a follow-up, repetition, or CRITICISM.

Return JSON: {category, search_query, direct_response, is_count_only, is_repetition, marketing_mode}

CATEGORIES: DEVELOPER, GREETING, INSTITUTIONAL.

STRICT RULES:
1. MARKETING MODE: If user is critical, compares colleges, or asks "why join?", set marketing_mode to true. 
   REWRITE search_query to find: "NAAC A+ Grade, NBA accreditation, placement records, ranking, RAISE center, and 1301 code".
2. DEVELOPER IDENTITY: If 'ram' is mentioned, set category to DEVELOPER.
3. REPETITION: If 'is_repetition' is true, find DEEPER details.
4. IDENTITY PROTECTION: Srinivasan/Principal = INSTITUTIONAL.
5. FOLLOW-UPS: Always prompt for more about Zenify, Zenpay, or Lorin RAG for DEVELOPER queries.
"""}, 
                {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
            ]
        }
        
        pre_res = ""
        async for chunk in self._safe_vercel_request(data_pre):
            pre_res += chunk
        p = self._safe_json_parse(pre_res)
        
        # 1B. DIRECT-TRAP KILLER (Master Rule Section 1A)
        # Never allow a 'direct_response' (refusal) for institutional names or personnel.
        is_greeting = p and p.get("category") == "GREETING"
        if p and p.get("direct_response") and is_greeting:
            yield p.get("direct_response"); return

        # 2. Context Retrieval
        search_query = p.get("search_query", user_query) if p else user_query
        intent = p.get("category", "INSTITUTIONAL") if p else "INSTITUTIONAL"
        
        context_chunks = await self.get_context(search_query, trace)
        
        # IDENTITY FAST-PASS (Master Rule Section 1A)
        # Force-recognize developer AND key student leaders
        lower_q = user_query.lower()
        if self.bm25 and (intent == "DEVELOPER" or "yogesh" in lower_q or "saqlin" in lower_q):
            profile_chunk = next((c for c in self.bm25.corpus if c["chunk_id"] == "PROFILE_RAMANATHAN_S"), None)
            yogesh_chunk = next((c for c in self.bm25.corpus if "msajce_incubation_chunk_06" in c["chunk_id"]), None)
            saqlin_chunk = next((c for c in self.bm25.corpus if "Professional_Societies" in c["metadata"].get("source_file", "")), None)
            
            if intent == "DEVELOPER" and profile_chunk: context_chunks.insert(0, profile_chunk)
            if "yogesh" in lower_q and yogesh_chunk: context_chunks.insert(0, yogesh_chunk)
            if "saqlin" in lower_q and saqlin_chunk: context_chunks.insert(0, saqlin_chunk)
        
        # Cleanup encoding artifacts and non-printable chars for LLM clarity
        def clean_text(t):
            t = re.sub(r'[^\x00-\x7F]+', ' ', t)
            return t.replace('  ', ' ').strip()

        context_text = "\n\n".join([f"[Source {i+1}]: {clean_text(c['text'])}" for i, c in enumerate(context_chunks[:5])])

        # 3. Generation (High-Confidence Institutional Advocacy)
        start_gen_time = time.time()
        is_count_only = p.get("is_count_only", False) if p else False
        is_repetition = p.get("is_repetition", False) if p else False
        marketing_mode = p.get("marketing_mode", False) if p else False
        
        system_prompt = f"""You are LORIN, the authoritative institutional AI for MSAJCE. 

STRICT RULES:
1. NO APOLOGIES: Never say "I don't have much information" or "I'm not sure" if context is present. Lead with FACTS.
2. FORMATTING: Use '•' for bullets. NO '*' or '-' symbols. NO '#' or '####' headers.
3. TONE: Professional, confident, and interactive. Use B2/C1 English.
4. MARKETING: {"You are in PEAK ADVOCATE mode. Emphasize: NAAC A+ Grade, NBA Accreditation, TNEA Code 1301, and our SIPCOT location." if marketing_mode else "Maintain institutional pride."}
5. LISTS: List all names clearly in bold. Use '•' for lists.
6. MEMORY: If this is a repetition ({is_repetition}), acknowledge previous info and provide deeper elite details.
7. FOLLOW-UP: End every response with a short, relevant question.
8. {"COUNT MODE: Provide a concise summary and count only." if is_count_only else ""}

CONTEXT:
{context_text}

History: {history if history else "None"}"""

        data_gen = {"model": self.generation_model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Query: {user_query}"}], "max_tokens": 1000}
        
        full_answer = ""
        line_buffer = ""
        async for chunk in self._safe_vercel_request(data_gen, stream=True):
            full_answer += chunk
            line_buffer += chunk
            
            if "\n" in line_buffer:
                lines = line_buffer.split("\n")
                for i in range(len(lines) - 1):
                    yield self._post_process(lines[i]) + "\n"
                line_buffer = lines[-1]
        
        if line_buffer:
            yield self._post_process(line_buffer)

        # FINAL TELEMETRY PAYLOAD (Master Rule Section 5C)
        end_time = time.time()
        yield {
            "type": "telemetry",
            "intent": intent,
            "sources": list(set([c.get("metadata", {}).get("source_file", "Unknown") for c in context_chunks])),
            "latency_ms": int((end_time - start_time) * 1000),
            "tokens": len(full_answer.split()) + len(context_text.split()) + 200 # Conservative estimate
        }
            
        trace.update(output=self._post_process(full_answer))

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
