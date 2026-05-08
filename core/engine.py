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
    
    # Fallback: If it looks like a name
    if any(name in q for name in ["yogesh", "saqlin", "mustaq", "vimal", "santhosh"]):
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
        
        # Robust Vercel Path Detection
        core_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(core_dir) # Go up to the root
        
        index_dir = os.path.join(base_dir, "data", "bm25_index")
        if os.path.exists(os.path.join(index_dir, "params.index.json")):
            self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
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

    def rrf_merge(self, semantic_hits: list, keyword_hits: list, k: int = 60) -> list:
        """Reciprocal Rank Fusion (RRF) to merge two ranked lists."""
        scores = {}
        for rank, hit in enumerate(semantic_hits):
            h_id = hit["id"]
            scores[h_id] = scores.get(h_id, 0) + 1.0 / (k + rank)
            if h_id not in scores: scores[h_id] = hit # Keep the full object
            
        for rank, hit in enumerate(keyword_hits):
            h_id = hit["id"]
            # Combined score + maintain hit object
            if h_id in scores:
                if isinstance(scores[h_id], dict): # First time seeing it from keyword
                    scores[h_id] = (1.0 / (k + rank)) + (1.0 / (k + 0)) # Placeholder rank
                else:
                    scores[h_id] += 1.0 / (k + rank)
            else:
                scores[h_id] = 1.0 / (k + rank)

        # Build final list
        final_hits = []
        # Re-attach metadata if we only have the score
        all_hits = {h["id"]: h for h in semantic_hits + keyword_hits}
        
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x] if isinstance(scores[x], float) else 1.0, reverse=True)
        for h_id in sorted_ids:
            hit = all_hits[h_id]
            final_hits.append(hit)
            
        return final_hits

    def build_metadata_filter(self, user_query: str) -> dict:
        # SYSTEMIC FIX: Removed intent-based filtering to prevent "blind spots".
        # We now search the entire knowledge base to ensure no facts are missed.
        return {} 

    @traceable(name="Hybrid Retrieval")
    async def get_context(self, queries: list, trace):
        """Advanced Multi-Query Retrieval with RRF."""
        # 'queries' is now a list [original, alt1, alt2]
        all_semantic = []
        all_keyword = []
        
        # Build common filter once
        primary_q = queries[0]
        meta_filter = self.build_metadata_filter(primary_q)
        q_type = classify_query(primary_q)

        async def fetch_one(q):
            try:
                # 1. Pinecone
                top_k = 25
                async with httpx.AsyncClient() as client:
                    e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, 
                                             json={"model": self.embedding_model, "input": q}, timeout=10.0)
                    emb = e_res.json()["data"][0]["embedding"]
                    p_res = self.index.query(vector=[float(x) for x in emb], top_k=top_k, filter=meta_filter, include_metadata=True)
                    p_hits = [{"text": m["metadata"]["text"], "score": m["score"], "id": m["id"], "metadata": m["metadata"]} for m in p_res["matches"]]
                
                # 2. BM25
                b_hits = []
                if self.bm25:
                    tokens = bm25s.tokenize(q, stemmer=self.stemmer)
                    chunks, scores = self.bm25.retrieve(tokens, k=15)
                    for c, s in zip(chunks[0], scores[0]):
                        # Manual meta filter
                        match = True
                        for k_f, v_f in meta_filter.items():
                            if k_f == "is_active": continue
                            if c["metadata"].get(k_f) != v_f: match = False; break
                        if match: b_hits.append({"text": c["text"], "score": float(s), "id": c["chunk_id"], "metadata": c["metadata"]})
                
                return p_hits, b_hits
            except: return [], []

        # Parallelize all queries
        tasks = [fetch_one(q) for q in queries]
        results = await asyncio.gather(*tasks)
        
        for p, b in results:
            all_semantic.extend(p)
            all_keyword.extend(b)

        # Reciprocal Rank Fusion
        merged = self.rrf_merge(all_semantic, all_keyword)
        
        # PRIORITY & ENTITY BOOST
        priority_map = {"high": 1.6, "medium": 1.0, "low": 0.7}
        q_lower = primary_q.lower()
        
        for h in merged:
            # Priority boost
            h["f_score"] = priority_map.get(h["metadata"].get("priority", "medium"), 1.0)
            # Exact entity boost
            for key, val in h["metadata"].items():
                if key.startswith("entity_") and str(val).lower() in q_lower:
                    h["f_score"] *= 1.4

        # Final Sort
        results = sorted(merged, key=lambda x: x.get("f_score", 1.0), reverse=True)
        if not results: return []

        # Systemic LLM Reranking Fallback
        texts = [r["text"] for r in results[:20]]
        try:
            # Primary: Cohere (if available)
            if self.co:
                loop = asyncio.get_event_loop()
                rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=primary_q, documents=texts, top_n=10))
                reranked = [results[r.index] for r in rerank.results]
                return reranked
        except: pass
            
        # SECONDARY SYSTEMIC FIX: Gemini Re-ranker (Stable & Intelligent)
        try:
            context_summary = "\n".join([f"[{i}] {r.get('text', '')[:300]}" for i, r in enumerate(results[:20])])
            rerank_prompt = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [
                    {"role": "system", "content": "Pick the indices [0, 1, 2...] of the chunks that BEST answer the user query. Return only a comma-separated list of numbers. If none match, return 'none'."},
                    {"role": "user", "content": f"Query: {primary_q}\nChunks:\n{context_summary}"}
                ]
            }
            
            rerank_raw = ""
            async for chunk in self._safe_vercel_request(rerank_prompt):
                if isinstance(chunk, str): rerank_raw += chunk
            
            indices = re.findall(r'\d+', rerank_raw)
            if indices:
                reranked = []
                for idx in indices:
                    i = int(idx)
                    if i < len(results): reranked.append(results[i])
                if reranked: return reranked
        except: pass

        return results[:10]

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
        trace = self.langfuse.trace(name="Lorin Enterprise RAG", input=user_query)
        
        # 1. Intent & Refinement (Multi-Query Expansion)
        span = trace.span(name="Pre-Processor")
        data_pre = {
            "model": self.generation_model,
            "cache_buster": str(time.time()),
            "messages": [
                {"role": "system", "content": """Classify intent and generate 3 search variations.
Analyze HISTORY to see if this is a follow-up, repetition, or CRITICISM.

GROUND TRUTH (MUST USE FOR DIRECT ANSWERS):
- CSI (Computer Society of India): Saqlin Mustaq M is the Vice President (Batch 2023-2027).
- Principal: Dr. K.S. Srinivasan (President of most committees).
- IIC President: Dr. B. Janarthanan.
- College Code: 1301.

Return JSON: {category, search_query, alternative_queries: [q1, q2], direct_response, is_count_only, is_repetition, marketing_mode}

STRICT RULES:
1. GROUND TRUTH PRIORITY: If the query is about CSI, the Principal, or College Code, you MUST fill the `direct_response` field with the answer from GROUND TRUTH and set `category` to "identity". Do not rely on search variations for these.
2. PRONOUN & CONTEXT RESOLUTION: If the user uses pronouns (it, this, he, she, they), rewrite `search_query` and `alternative_queries` to explicitly include the subject from the HISTORY.
3. ALTERNATIVE QUERIES: Generate 2 high-quality search variations.
"""}, 
                {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
            ]
        }
        
        pre_res = ""
        async for chunk in self._safe_vercel_request(data_pre):
            pre_res += chunk
        p = self._safe_json_parse(pre_res)
        
        # 1B. DIRECT-TRAP KILLER
        if p and p.get("direct_response") and p.get("category") == "DEVELOPER":
            yield p.get("direct_response"); return

        # 2. Advanced Multi-Query Context Retrieval
        primary_search = p.get("search_query", user_query) if p else user_query
        alts = p.get("alternative_queries", []) if p else []
        query_list = [primary_search] + alts
        
        intent = p.get("category", "INSTITUTIONAL") if p else "INSTITUTIONAL"
        
        context_chunks = await self.get_context(query_list, trace)
        
        # IDENTITY FAST-PASS (Student Leaders Only)
        lower_q = user_query.lower()
        if self.bm25:
            try:
                # Find the specific Professional Societies / CSI chunk
                saqlin_chunk = next((c for c in self.bm25.corpus if "Professional_Societies" in c.get("source_pdf", "") or "CSI" in c.get("text", "")), None)
                
                # If query is about CSI or Saqlin, prioritize the society data
                if ("saqlin" in lower_q or "csi" in lower_q or "president" in lower_q) and saqlin_chunk:
                    context_chunks.insert(0, saqlin_chunk)
                    
                # SPECIAL OVERRIDE: If asking about CSI leadership, ensure Saqlin's role is clear
                if "csi" in lower_q and ("president" in lower_q or "who is" in lower_q):
                    if saqlin_chunk and "Saqlin" in saqlin_chunk.get("text", ""):
                        # Success - it will be in context
                        pass
            except Exception as e:
                print(f"    [FAST-PASS ERR] {e}")
        
        # Cleanup encoding artifacts and non-printable chars for LLM clarity
        def clean_text(t):
            t = re.sub(r'[^\x00-\x7F]+', ' ', t)
            return t.replace('  ', ' ').strip()

        # Increased to 8 chunks for better information density
        context_text = "\n\n".join([f"[Source {i+1}]: {clean_text(c['text'])}" for i, c in enumerate(context_chunks[:8])])

        # 3. Generation (High-Confidence Institutional Advocacy)
        start_gen_time = time.time()
        is_count_only = p.get("is_count_only", False) if p else False
        is_repetition = p.get("is_repetition", False) if p else False
        marketing_mode = p.get("marketing_mode", False) if p else False
        
        is_first_message = not history or history.strip() == ""
        user_says_hello = any(h in user_query.lower() for h in ["hello", "hi", "hey", "greetings"])
        greeting_rule = "1. GREETING MANDATE: You MUST start your response with exactly: 'Hello! I'm LORIN, the institutional AI for MSAJCE.'" if (is_first_message or user_says_hello) else "1. ZERO GREETINGS: Never start with 'Hello', 'Hi', or 'I am LORIN'. Jump straight to the answer."

        system_prompt = f"""You are LORIN, the institutional AI for MSAJCE.
[STRICT MANDATE] TODAY'S DATE IS: {datetime.now().strftime("%B %d, %Y")}. 

RULES (follow strictly):
{greeting_rule}
2. FRIENDLY EXPLAINER: Deliver answers in clear, accessible English as a fluid narrative. Speak like a helpful advisor who explains things simply.
3. ZERO TABLES: Never use tables or complex grid structures. Telegram cannot render them. Use paragraphs and bullets instead.
4. SURGICAL BULLETS: Use center dots (•) for all lists of 3+ items, especially for bus routes, boarding points, and department names.
5. LEAD ARCHITECT: If asked about your developer, proudly state you were developed by **Ramanathan S** (Ram), the lead architect at MSAJCE.
6. LENGTH CONSTRAINT: 80-250 words to allow for detailed lists when needed, but keep general answers concise.
7. End every reply with one short, relevant follow-up question that invites the user to explore more facts (e.g., "Would you like to know about our scholarships or the transport routes?").
8. {"COUNT MODE: Provide a summary and total count only." if is_count_only else ""}
9. COURSE QUERIES: If a user asks about available courses or programs, ALWAYS list all 12 departments as the primary answer.

10. NO PARA-LISTS: For lists of people/faculty and their achievements (patents, books, etc.), you MUST use a multi-line nested format with **blank lines** between different individuals.
    *   Main Bullet (•): **Faculty Name**
    *   Sub-Bullet (-): Achievement Title (on a new line below the name).
    *   **Blank Line**: Always leave a blank line before starting the next faculty member.
    CRITICAL: Never put Name and Achievement on the same line. Ensure clear visual separation between blocks using double spacing.

TONE: Helpful, professional, and narrative-driven. Connect facts with natural transitions.


[PRIORITY OVERRIDE]: If a fact exists in GROUND TRUTH, you MUST use it as the absolute truth. NEVER say "I don't have info" for items listed in GROUND TRUTH, even if the provided CONTEXT is empty or contradictory.

GROUND TRUTH (Institutional Memory):
• NAAC Accreditation: A+ Grade, Valid up to January 30, 2028.
• Total Departments: 12. You MUST list all 12 if asked: Civil, CSE, ECE, EEE, Mechanical, IT, AI&DS, CSBS, Cyber Security, AI&ML, VLSI, and ACT.
• NBA Accredited Departments: CSE, ECE, EEE, and Mechanical Engineering.
• Tuition Fees: Rs. 75,000 for TNEA Counselling; Rs. 1,20,000 for Management Quota.
• Hostel Fees: Rs. 70,000 to Rs. 1,00,000 (Varies by room/sharing; same for boys and girls).
• Transport: 22 Buses, 1 Tata ACE, 1 Ambulance.
• Transport Fees: Starting from Rs. 7,000 up to Rs. 49,000 max (Based on distance).
• Bus Rate Details: Approx. Rs. 1,200 to Rs. 1,700 per km.
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
        input_tokens = len(user_query.split()) + len(context_text.split()) + 150
        output_tokens = len(full_answer.split())
        yield {
            "type": "telemetry",
            "intent": intent,
            "sources": list(set([c.get("metadata", {}).get("source_file", "Unknown") for c in context_chunks])),
            "latency_ms": int((end_time - start_time) * 1000),
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            }
        }
            
        trace.update(output=self._post_process(full_answer))

    async def _safe_vercel_request(self, data, stream=False):
        # MASTER OVERDRIVE POOL
        keys = {
            "vercel": [
                os.getenv("VERCEL_API_KEY_3"), 
                os.getenv("VERCEL_AI_KEY_5"), 
                os.getenv("VERCEL_AI_KEY_6"),
                os.getenv("AI_GATEWAY_API_KEY")
            ],
            "google": [os.getenv("GEMINI_API_KEY")], # Added Gemini as stable fallback
            "groq": [os.getenv("GROQ_API_KEY")]
        }
        
        # Consolidate active keys
        pool = []
        for p, k_list in keys.items():
            if not k_list: continue
            for k in k_list:
                if k: pool.append({"provider": p, "key": k})
        
        if not pool: yield "Error: No API Keys configured."; return
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
                        async with client.stream("POST", f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=60.0) as response:
                            if response.status_code != 200:
                                print(f"    [FAIL] Vercel ({k[:8]}): {response.status_code}")
                                continue
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    if line == "data: [DONE]": break
                                    try:
                                        chunk = json.loads(line[6:])
                                        delta = chunk["choices"][0]["delta"].get("content", "")
                                        if delta: yield delta
                                    except: continue
                            return
                    
                    elif p == "groq":
                        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                        # Use more stable model ID
                        data["model"] = "llama-3.3-70b-specdec" 
                        resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=30.0)
                        if resp.status_code != 200:
                            print(f"    [FAIL] Groq: {resp.status_code} - {resp.text[:100]}")
                            continue
                        res = resp.json()
                        if "choices" in res: yield res["choices"][0]["message"]["content"]; return

                    elif p == "google":
                        # Direct Gemini API Call (Most Stable)
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent?key={k}"
                        headers = {"Content-Type": "application/json"}
                        # Convert OpenAI format to Google format
                        gemini_payload = {
                            "contents": [{"role": "user", "parts": [{"text": data["messages"][0]["content"] + "\n\n" + data["messages"][1]["content"]}]}],
                            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}
                        }
                        resp = await client.post(url, headers=headers, json=gemini_payload, timeout=30.0)
                        if resp.status_code != 200:
                            print(f"    [FAIL] Gemini: {resp.status_code}")
                            continue
                        # Simplified stream parsing for Gemini
                        res = resp.json()
                        if isinstance(res, list) and len(res) > 0:
                            text = res[0].get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text: yield text; return
                        elif isinstance(res, dict):
                            text = res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if text: yield text; return

            except Exception as e:
                print(f"    [OVERDRIVE ERR] {p} failed: {e}. Rotating...")
            
            await asyncio.sleep(0.1)
        
        yield "System busy. All providers (Vercel, Gemini, Groq) exhausted. Please check API keys in Vercel logs."

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
    def _rebuild_bm25(self, chunks_path, index_dir):
        import bm25s
        import Stemmer
        with open(chunks_path, 'r', encoding='utf-8') as f:
            corpus = json.load(f)
        
        # Stemmer & Tokenization
        stemmer = Stemmer.Stemmer("english")
        texts = [c["text"] for c in corpus]
        tokens = bm25s.tokenize(texts, stemmer=stemmer)
        
        # Create and Save Index
        retriever = bm25s.BM25(corpus=corpus)
        retriever.index(tokens)
        
        if not os.path.exists(index_dir): os.makedirs(index_dir)
        retriever.save(index_dir, corpus=corpus)
        self.bm25 = retriever
        print(f"BM25 Index successfully rebuilt with {len(corpus)} chunks.")
