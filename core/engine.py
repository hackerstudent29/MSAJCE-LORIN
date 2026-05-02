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

GROUND TRUTH (Use this for direct_response if needed):
• NAAC: A+ Grade, valid until Jan 30, 2028.
• NBA Accredited: CSE, ECE, EEE, Mechanical.
• Highest Salary (2024): 12 LPA.
• Top Recruiters: Fidelity, Intel, Amazon, Zoho, TCS, CTS.
• Code: 1301.
• Hostel: Needs written HOD/Warden permission for outings.
• Scholarship: 180+ cutoff for merit; 10% discount for girls.
• Transport: MTC 105 (Tambaram), 102, 570 (OMR).
• Events: 'Sathak Thiruvizha' (Cultural), 'HABIBI' (Symposium).
• Lateral Entry: TN-LEA counselling.

CATEGORIES: DEVELOPER, GREETING, INSTITUTIONAL.

STRICT RULES:
1. MARKETING MODE: If user is critical, compares colleges, or asks "why join?", set marketing_mode to true. 
   REWRITE search_query to find: "NAAC A+ Grade, NBA accreditation, placement records, ranking, RAISE center, and 1301 code".
2. DEVELOPER IDENTITY: If 'ram' or 'ramanathan' is mentioned, set category to DEVELOPER and refer to his official portfolio: https://ramanathan-s.vercel.app/.
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
        
        system_prompt = f"""You are LORIN, the institutional AI for MSAJCE.
[STRICT MANDATE] TODAY'S DATE IS: {datetime.now().strftime("%B %d, %Y")}. 
You MUST use this date for all academic year, batch, and current event calculations.

RULES (follow strictly):
1. INTERACTIVE NARRATIVE: Speak like a high-end educational counselor. Avoid starting every message with "Hello" or "Hey there." Instead, dive into the conversation naturally (e.g., "You'll find that our campus infrastructure is designed for...", "It's interesting you asked about the labs, because...").
2. MARKETING TONE: Don't just list facts—explain the *benefit*. (e.g., Mentioning SIPCOT IT Park? Explain that it means being surrounded by future employers).
3. SELECTIVE BULLETS: Use bullet points '•' ONLY when listing 3 or more distinct items. For everything else, use smooth, professional paragraphs.
4. LINGUISTIC MIRRORING: Default to B1 Casual English. Mirror C1/C2 if the user uses it.
5. LENGTH CONSTRAINT: 80-120 words (Sweet Spot). Min 20, Max 150.
6. End every reply with one short, relevant follow-up question.
7. {"COUNT MODE: Provide a summary and total count only." if is_count_only else ""}

TONE: Enthusiastic institutional advocate. Speak with a natural, explaining flow. Never sound like a list-reader. Be warm, persuasive, and authoritative.
7. {"COUNT MODE: Provide a summary and total count only." if is_count_only else ""}

TONE: Friendly and adaptive. Use accessible English for most, but match the intellectual depth of advanced users when prompted by their vocabulary.

[PRIORITY OVERRIDE]: If a fact exists in GROUND TRUTH, you MUST use it as the absolute truth. NEVER say "I don't have info" for items listed in GROUND TRUTH, even if the provided CONTEXT is empty or contradictory.

GROUND TRUTH (Institutional Memory):
• NAAC Accreditation: A+ Grade, Valid up to January 30, 2028.
• NBA Accredited Departments: CSE, ECE, EEE, and Mechanical Engineering.
• Tuition Fees: Rs. 75,000 for TNEA Counselling; Rs. 1,20,000 for Management Quota.
• Hostel Fees: Rs. 70,000 to Rs. 1,00,000 (Varies by room/sharing; same for boys and girls).
• Transport Fees: Starting from Rs. 7,000 up to Rs. 49,000 max (Based on distance).
• Bus Rate Details: Approx. Rs. 1,200 to Rs. 1,700 per km. (Note: These are estimates; contact the Transport Committee for exact accuracy).
• Highest Salary (2024 Batch): Rs. 12 Lakhs Per Annum (LPA).
• Top Recruiters: Fidelity National Financial, Intel, Amazon, Zoho, TCS, and CTS.
• Admission Code: 1301. AI&ML Seats: 30 (15 Management, 15 Government).
• Hostel Outing Rules: Written permission from HOD and Warden is mandatory for all outings. Outstation travel requires written warden approval.
• Scholarships: Merit waivers for 180+ cut-off; 10% tuition fee discount for all female students. Supports AICTE Pragati & Saksham.
• Anti-Ragging: Zero tolerance policy, headed by the Principal with dedicated monitoring squads.
• Transport: MTC 105 (Tambaram), 102, 570 (OMR). College fleet covers Kanchipuram, Chengalpattu, Thiruvallur.
• Events: 'Sathak Thiruvizha' (Cultural), 'HABIBI' (Symposium), 'Ciphera' (CTF).
• Student Council: President, Secretary, Coordinators; overseen by Student Affairs.
• Lateral Entry: Via TN-LEA counselling for Diploma/B.Sc. Math holders.

CONTEXT:
{context_text}

History: {history if history else "None"}"""

        data_gen = {
            "model": self.generation_model, 
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Query: {user_query}"}], 
            "max_tokens": 1000,
            "temperature": 0.7 # HYPER-VARIETY: Ensures unique phrasing every time
        }
        
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
        # MASTER OVERDRIVE POOL
        keys = {
            "vercel": [os.getenv("VERCEL_API_KEY_3"), os.getenv("VERCEL_AI_KEY_5"), os.getenv("AI_GATEWAY_API_KEY")],
            "groq": [os.getenv("GROQ_API_KEY")],
            "openrouter": [os.getenv("OPENROUTER_API_KEY")]
        }
        
        # Consolidate active keys
        pool = []
        for p, k_list in keys.items():
            for k in k_list:
                if k: pool.append({"provider": p, "key": k})
        
        if not pool: yield "Error: No API Keys"; return
        if not hasattr(self, "_pool_idx"): self._pool_idx = 0
        
        for attempt in range(len(pool) * 2):
            node = pool[self._pool_idx % len(pool)]
            self._pool_idx += 1
            
            p, k = node["provider"], node["key"]
            try:
                async with httpx.AsyncClient() as client:
                    if p == "vercel":
                        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                        if stream: data["stream"] = True
                        if stream:
                            async with client.stream("POST", f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0) as response:
                                async for line in response.aiter_lines():
                                    if line.startswith("data: "):
                                        if line == "data: [DONE]": break
                                        try:
                                            chunk = json.loads(line[6:])
                                            delta = chunk["choices"][0]["delta"].get("content", "")
                                            if delta: yield delta
                                        except: continue
                                return
                        else:
                            resp = await client.post(f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0)
                            res = resp.json()
                            if "choices" in res: yield res["choices"][0]["message"]["content"]; return
                    
                    elif p == "groq":
                        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                        data["model"] = "llama-3.3-70b-specdec"
                        resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30.0)
                        res = resp.json()
                        if "choices" in res: yield res["choices"][0]["message"]["content"]; return

                    elif p == "openrouter":
                        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                        data["model"] = "google/gemini-2.0-flash-001"
                        resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30.0)
                        res = resp.json()
                        if "choices" in res: yield res["choices"][0]["message"]["content"]; return

            except Exception as e:
                print(f"    [OVERDRIVE ERR] {p} failed: {e}. Rotating...")
            
            await asyncio.sleep(0.1)
        
        yield "System busy. All providers exhausted."

    async def _groq_request(self, data):
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key: yield "Error: No Groq Key"; return
        
        headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
        # Map to Groq models
        data["model"] = "llama-3.3-70b-specdec" 
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30.0)
                res_json = resp.json()
                if "choices" in res_json:
                    yield res_json["choices"][0]["message"]["content"]
                else:
                    print(f"    [GROQ ERR] {res_json}")
        except Exception as e:
            print(f"    [GROQ EXCEPTION] {e}")
