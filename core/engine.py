import os
os.environ['LANGSMITH_TRACING'] = 'false'
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

load_dotenv()
os.environ['LANGSMITH_TRACING'] = 'false'
logger = logging.getLogger(__name__)

# ── Master Query Classifiers (v2 — 7 Query Types) ────────────────────────────
LIST_SIGNALS = ["list", "all", "who are", "names of", "how many", "give me all", "show all", "everyone", "full list"]
PERSON_SIGNALS = ["who is", "tell me about", "who heads", "who runs", "principal", "hod", "head of", "professor", "faculty", "staff"]
ROUTE_SIGNALS = ["bus", "route", "stop", "timing", "transport", "ar8", "tambaram", "which bus", "bus number"]
RULE_SIGNALS = ["allowed", "not allowed", "policy", "rule", "can i", "hostel", "attendance", "regulation"]
DEPT_NAMES = ["cse", "it", "ece", "eee", "civil", "mech", "aids", "aiml", "cyber", "csbs", "sh"]

def classify_query(query: str) -> str:
    q = query.lower()
    if any(s in q for s in ROUTE_SIGNALS) or "ar8" in q or "ar " in q: return "ROUTE_QUERY"
    if any(s in q for s in ["who is", "tell me about", "hod", "principal", "yogesh", "ramanathan"]): return "PERSON_QUERY"
    if any(s in q for s in RULE_SIGNALS): return "RULE_QUERY"
    if any(d in q for d in DEPT_NAMES): return "DEPARTMENT_QUERY"
    if any(s in q for s in LIST_SIGNALS): return "LIST_QUERY"
    if q.strip() in ["yes", "no", "ok", "tell me more", "elaborate"]: return "ELABORATION_QUERY"
    return "GENERAL_QUERY"

def clean_prose(text):
    """Converts markdown bullets and artifacts into fluid prose."""
    if not text: return ""
    text = re.sub(r'^[ \t]*[*+-][ \t]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text).strip()
    return text

def format_query_for_embedding(query: str, query_type: str, department: str = "") -> str:
    """
    Wraps the user query in the same super_chunk_text format used
    at ingest time. This aligns the query vector with chunk vectors
    so cosine similarity is accurate.
    """
    dept_line = department if department else "General"
    return (
        f"This information is from the MSAJCE institution, specifically the "
        f"{dept_line} department. Section: {query_type.replace('_', ' ').title()}.\n\n"
        f"SUMMARY: A student is asking about {query}\n"
        f"QUESTIONS: {query}\n"
        f"CONTENT: {query}"
    )

class RAGEngine:
    def __init__(self):
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            self.pc = Pinecone(api_key=pc_key)
            for idx_name in ["raglorin"]:
                try:
                    self.index = self.pc.Index(idx_name)
                    self.index.describe_index_stats()
                    break
                except: continue
            else: self.index = None
        except: self.index = None

        try:
            self.co = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
        except: self.co = None

        self.stemmer = Stemmer.Stemmer("english")
        core_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(core_dir)

        for bm25_dir_name in ["bm25_index_v2", "bm25_index"]:
            index_dir = os.path.join(base_dir, "data", bm25_dir_name)
            try:
                if os.path.exists(os.path.join(index_dir, "params.index.json")):
                    self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
                    break
            except: continue
        else: self.bm25 = None

        self.generation_model = "google/gemini-2.0-flash-001"
        self.embedding_model = "openai/text-embedding-3-small"

        for gt_name in ["ground_truth_v2.json", "ground_truth.json"]:
            gt_path = os.path.join(base_dir, "data", gt_name)
            if os.path.exists(gt_path):
                self.ground_truth_path = gt_path
                break
        self.ground_truth = self._load_ground_truth()

        # Initialize Redis for security/rate-limiting
        try:
            self.redis = Redis.from_env()
        except:
            self.redis = None

    def _load_ground_truth(self):
        if os.path.exists(self.ground_truth_path):
            try:
                with open(self.ground_truth_path, 'r') as f:
                    data = json.load(f)
                now = datetime.now()
                fresh_data = {}
                for key, fact in data.items():
                    expiry_str = fact.get("valid_until", "2099-12-31")
                    expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if now < expiry:
                        val = fact.get("value")
                        fresh_data[key.lower()] = val
                        if "president" in key.lower(): fresh_data["president"] = val
                        if "yogesh" in str(val).lower(): fresh_data["yogesh"] = val
                        if "ramanathan" in str(val).lower(): fresh_data["ramanathan"] = val
                return fresh_data
            except: pass
        return {}

    def _safe_json_parse(self, text):
        try: return json.loads(text.strip())
        except:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None

    def rrf_merge(self, semantic_hits, keyword_hits, k=60):
        scores = {}
        all_hits = {}
        for i, hit in enumerate(semantic_hits):
            doc_id = hit["id"]
            all_hits[doc_id] = hit
            if doc_id not in scores: scores[doc_id] = 0
            scores[doc_id] += 1.0 / (k + i + 1)
        for i, hit in enumerate(keyword_hits):
            doc_id = hit["id"]
            if doc_id not in all_hits: all_hits[doc_id] = hit
            if doc_id not in scores: scores[doc_id] = 0
            scores[doc_id] += (1.5 / (k + i + 1)) # BM25 Weight 1.5x
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for h_id in sorted_ids:
            hit = all_hits[h_id]
            hit["rrf_score"] = scores[h_id]
            results.append(hit)
        return results

    def extract_entities(self, query: str) -> list:
        entities = []
        lower_q = query.lower()
        keywords = ["csi", "ieee", "sae", "bus", "route", "faculty", "placement"]
        for k in keywords:
            if k in lower_q: entities.append(k)
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entities.extend([n.lower() for n in names])
        return list(set(entities))

    @traceable(name="Hybrid Retrieval")
    async def get_context(self, queries: list, trace, depth: int = 20):
        all_semantic, all_keyword = [], []
        primary_q = queries[0]
        
        async def fetch_one(q):
            p_hits, b_hits = [], []
            try:
                emb = None
                # Order: working keys first (KEY_6 is out of funds)
                vercel_keys = [os.getenv("VERCEL_AI_KEY_5"), os.getenv("VERCEL_API_KEY_3"), os.getenv("AI_GATEWAY_API_KEY"), os.getenv("VERCEL_AI_KEY_6")]
                async with httpx.AsyncClient() as client:
                    for k in vercel_keys:
                        if not k: continue
                        try:
                            headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                            
                            query_type = classify_query(q)
                            dept = ""
                            for d in DEPT_NAMES:
                                if d in q.lower():
                                    dept = d.upper()
                                    break
                            formatted_q = format_query_for_embedding(q, query_type, dept)
                            
                            # CRITICAL: dimensions=1024 must match Pinecone index dimension
                            e_res = await client.post("https://ai-gateway.vercel.sh/v1/embeddings", headers=headers, json={"model": self.embedding_model, "input": formatted_q}, timeout=5.0)
                            if e_res.status_code == 200:
                                emb = e_res.json()["data"][0]["embedding"]; break
                        except: continue

                if self.bm25:
                    q_clean = re.sub(r'[^\w\s]', '', q.lower())
                    tokens = bm25s.tokenize(q_clean, stemmer=self.stemmer, show_progress=False)
                    chunks, scores = self.bm25.retrieve(tokens, k=15, show_progress=False)
                    for c, s in zip(chunks[0], scores[0]):
                        if isinstance(c, dict): b_hits.append({"text": c.get("text", ""), "score": float(s), "id": c.get("chunk_id", ""), "metadata": c.get("metadata", {})})
                
                if emb and self.index:
                    p_res = self.index.query(vector=[float(x) for x in emb], top_k=depth, include_metadata=True)
                    p_hits = [{"text": m["metadata"]["text"], "score": m["score"], "id": m["id"], "metadata": m["metadata"]} for m in p_res["matches"]]
                return p_hits, b_hits
            except: return [], []

        results = await asyncio.gather(*[fetch_one(q) for q in queries])
        for p, b in results:
            all_semantic.extend(p); all_keyword.extend(b)

        merged = self.rrf_merge(all_semantic, all_keyword)
        priority_map = {"critical": 2.0, "high": 1.6, "medium": 1.0, "low": 0.7}
        q_lower = primary_q.lower()
        for h in merged:
            h["f_score"] = h.get("rrf_score", 0.01) * priority_map.get(h["metadata"].get("priority", "medium"), 1.0)
            if any(str(val).lower() in q_lower for val in h["metadata"].values() if isinstance(val, (str, list))):
                h["f_score"] *= 1.4

        results = sorted(merged, key=lambda x: x.get("f_score", 1.0), reverse=True)
        if not results: return []
        texts = [r["text"] for r in results[:20]]
        reranked = None
        try:
            if self.co:
                loop = asyncio.get_event_loop()
                rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=primary_q, documents=texts, top_n=10))
                reranked = [results[r.index] for r in rerank.results]
        except: pass
        if not reranked: reranked = results[:10]
        return reranked

    def _post_process(self, text: str) -> str:
        text = re.sub(r'(?i)\bblank\s+line\b', '', text)
        text = re.sub(r'\[.*?\]', '', text) 
        text = re.sub(r'^#+.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[ \t]*[*+-][ \t]+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    async def query_stream(self, user_query, history=None, user_level="student", thinking=False):
        start_time = time.time()
        intent = classify_query(user_query)
        
        # 1. IMMEDIATE GREETING BYPASS
        if intent == "GREETING":
            resp = "Hello! I'm LORIN, the institutional AI for MSAJCE. I can help you with information about faculty, bus routes, departments, and college policies. How can I assist you today?"
            yield resp
            yield {
                "type": "telemetry",
                "latency_ms": int((time.time() - start_time) * 1000),
                "tokens": 42,
                "intent": "GREETING",
                "sources": ["System Cache"]
            }
            return

        queries = [user_query]
        if intent == "ELABORATION_QUERY" and history:
            last_lines = history.split("\n")
            anchor = next((l.replace("assistant:", "").strip()[:100] for l in reversed(last_lines) if "assistant:" in l.lower()), "")
            if anchor: queries.append(f"{anchor} {user_query}")

        # [HyDE & PRE-CLASSIFY]
        gt_context = "\n".join([f"- {k.upper()}: {v}" for k, v in self.ground_truth.items()])
        data_pre = {
            "model": "google/gemini-2.0-flash-exp:free",
            "messages": [{"role": "system", "content": f"Classify intent and generate a 1-sentence 'Hypothetical Perfect Answer' (HyDE).\nGROUND TRUTH:\n{gt_context}\nReturn JSON: {{category, search_query, hyde_answer, direct_response}}"}, {"role": "user", "content": user_query}]
        }
        pre_res = ""
        try:
            async for chunk in self._safe_vercel_request(data_pre): pre_res += chunk
            p = self._safe_json_parse(pre_res)
            if p:
                # ONLY use direct_response for non-entity queries to ensure entities get full 80-100 word RAG treatment
                if p.get("direct_response") and intent not in ["PERSON_QUERY", "DEPARTMENT_QUERY"]:
                    dr = p.get("direct_response")
                    yield dr
                    input_est = (len(gt_context) + len(user_query)) // 4
                    output_est = len(dr.split()) * 1.5
                    yield {
                        "type": "telemetry",
                        "latency_ms": int((time.time() - start_time) * 1000),
                        "tokens": int(input_est + output_est) + 150,
                        "intent": intent,
                        "sources": ["Ground Truth Vault"]
                    }
                    return
                if p.get("hyde_answer") and intent == "GENERAL_QUERY":
                    queries.append(p.get("hyde_answer"))
        except: pass

        context_chunks = await self.get_context(queries, None)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])
        sources = list(set([c['metadata'].get('page_title', c['metadata'].get('filename', 'Institutional Source')) for c in context_chunks]))

        system_prompt = f"""You are LORIN, the institutional AI for MSAJCE.
STRICT OPERATIONAL RULES:
1. GREETING BYPASS: DO NOT GREET THE USER. DO NOT say "Hello", "Hi", or "I'm LORIN" if the user has asked a specific question.
2. DIRECT RESPONSE: Start your response IMMEDIATELY with the requested information. No preamble.
3. ENTITY RESPONSE RULES (CRITICAL — for any person, faculty, HOD, principal, etc.):
   a) Count ALL the information you have about this entity from CONTEXT and GROUND TRUTH.
   b) If the total info is 100 words or LESS: Give EVERYTHING you have in ONE complete answer. Do not hold back any detail.
   c) If the total info is MORE than 100 words: Write a rich summary of 80-100 words covering name, designation, department, qualification, and key highlights. Then END with a specific follow-up like: "Would you like to know more about his research interests, publications, or contact details?"
   d) NEVER give a one-liner like "Dr. X is the Principal." — that is UNACCEPTABLE. Always provide the fullest answer possible within these rules.
4. NARRATIVE FLOW: Write in fluid, natural paragraphs. Use pronouns (He/She/They) after the first mention.
5. STRICT ROUTE VERIFICATION: For bus route queries (AR1-AR10, R22), verify every stop belongs to that specific route in CONTEXT.
6. SURGICAL FOCUS: Answer ONLY what is asked. For person queries, provide a cohesive biography/summary, not fragmented facts.
7. FORMATTING: Use center dots (•) ONLY for actual lists. NEVER use tables.
8. IDENTITY: You were developed by Ramanathan S (Ram). Only mention this if explicitly asked.
9. End with a relevant follow-up question.

GROUND TRUTH:
{gt_context}

CONTEXT:
{context_text}"""


        # Construct messages with history
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for line in history.split("\n"):
                if line.startswith("User: "):
                    messages.append({"role": "user", "content": line.replace("User: ", "")})
                elif line.startswith("Bot: "):
                    messages.append({"role": "assistant", "content": line.replace("Bot: ", "")})
        
        messages.append({"role": "user", "content": user_query})

        data_gen = {
            "model": self.generation_model,
            "messages": messages,
            "temperature": 0.4
        }
        
        full_answer = ""
        async for chunk in self._safe_vercel_request(data_gen, stream=True):
            full_answer += chunk
            yield self._post_process(chunk)

        # FINAL TELEMETRY YIELD
        latency = (time.time() - start_time) * 1000
        input_est = (len(system_prompt) + len(user_query) + (len(history) if history else 0)) // 3.8
        output_est = len(full_answer.split()) * 1.5
        total_tokens = max(int(input_est + output_est), 150)
        
        yield {
            "type": "telemetry",
            "latency_ms": int(latency),
            "tokens": total_tokens,
            "intent": intent,
            "sources": sources[:3]
        }

    async def _safe_vercel_request(self, data, stream=False):
        vercel_keys = [os.getenv("VERCEL_API_KEY_3"), os.getenv("VERCEL_AI_KEY_5"), os.getenv("VERCEL_AI_KEY_6"), os.getenv("AI_GATEWAY_API_KEY")]
        for k in vercel_keys:
            if not k: continue
            try:
                headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                url = f"https://ai-gateway.vercel.sh/v1/chat/completions"
                async with httpx.AsyncClient() as client:
                    if stream:
                        data["stream"] = True
                        async with client.stream("POST", url, headers=headers, json=data, timeout=30.0) as resp:
                            if resp.status_code == 200:
                                async for line in resp.aiter_lines():
                                    if line.startswith("data: "):
                                        if "[DONE]" in line: break
                                        try:
                                            chunk = json.loads(line[6:])
                                            content = chunk["choices"][0]["delta"].get("content", "")
                                            if content: yield content
                                        except: pass
                                return
                    else:
                        resp = await client.post(url, headers=headers, json=data, timeout=30.0)
                        if resp.status_code == 200:
                            yield resp.json()["choices"][0]["message"]["content"]; return
            except: continue
        yield "System busy. Please try again."
