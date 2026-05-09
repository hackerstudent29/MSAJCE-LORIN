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
from langfuse import Langfuse

load_dotenv()
os.environ['LANGSMITH_TRACING'] = 'false'
logger = logging.getLogger(__name__)

# ── Master Query Classifiers (v2 — 7 Query Types) ────────────────────────────
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
ROUTE_SIGNALS = [
    "bus", "route", "stop", "timing", "transport", "ar8", "tambaram",
    "kanchipuram", "chengalpattu", "which bus", "bus number"
]
RULE_SIGNALS = [
    "allowed", "not allowed", "policy", "rule", "can i", "hostel",
    "attendance", "regulation", "prohibited", "dress code"
]
LIST_DOC_SIGNALS = [
    "documents needed", "what documents", "documents required",
    "what to carry", "checklist", "list of", "requirements"
]
DEPT_NAMES = [
    "cse", "it", "ece", "eee", "civil", "mech", "aids", "aiml",
    "cyber", "csbs", "sh", "vlsi", "act", "computer science",
    "information technology", "electronics", "electrical", "mechanical"
]

# ── RETRIEVAL_MAP: Exact k-values per query type ──────────────────────────────
RETRIEVAL_MAP = {
    "PERSON_QUERY":     {"semantic_k": 8,  "bm25_k": 5,  "final_k": 5,  "filter": {"node_type": "PERSON"}},
    "FACT_QUERY":       {"semantic_k": 10, "bm25_k": 8,  "final_k": 5,  "filter": {}},
    "RULE_QUERY":       {"semantic_k": 12, "bm25_k": 6,  "final_k": 6,  "filter": {"chunk_type": "rule"}},
    "LIST_QUERY":       {"semantic_k": 8,  "bm25_k": 5,  "final_k": 5,  "filter": {"chunk_type": "list"}},
    "ROUTE_QUERY":      {"semantic_k": 8,  "bm25_k": 8,  "final_k": 5,  "filter": {}},
    "DEPARTMENT_QUERY": {"semantic_k": 15, "bm25_k": 8,  "final_k": 8,  "filter": {}},
    "GENERAL_QUERY":    {"semantic_k": 25, "bm25_k": 15, "final_k": 8,  "filter": {}},
    # Legacy fallback types (map to v2 equivalents)
    "person":           {"semantic_k": 8,  "bm25_k": 5,  "final_k": 5,  "filter": {}},
    "list":             {"semantic_k": 8,  "bm25_k": 5,  "final_k": 5,  "filter": {}},
    "stat":             {"semantic_k": 10, "bm25_k": 8,  "final_k": 5,  "filter": {}},
    "fact":             {"semantic_k": 10, "bm25_k": 8,  "final_k": 5,  "filter": {}},
}

# ── Priority score multipliers ────────────────────────────────────────────────
PRIORITY_MULTIPLIER = {
    "critical": 1.4,
    "high":     1.2,
    "medium":   1.0,
    "low":      0.8,
}

def classify_query(query: str) -> str:
    """v2 Query Classifier — 7 types."""
    q = query.lower()
    # Person detection (hardened for student leaders & names)
    if any(s in q for s in ["who is", "who are", "wo is", "ho is", "tell me about",
                             "contact of", "hod of", "warden", "president", "secretary", "yogesh", "saqlin", "mustaq"]):
        return "PERSON_QUERY"
    # Route detection
    if any(s in q for s in ROUTE_SIGNALS):
        return "ROUTE_QUERY"
    # Rule/Policy detection
    if any(s in q for s in RULE_SIGNALS):
        return "RULE_QUERY"
    # List/Document detection
    if any(s in q for s in LIST_DOC_SIGNALS) or any(s in q for s in LIST_SIGNALS):
        return "LIST_QUERY"
    # Department-specific detection
    if any(d in q for d in DEPT_NAMES):
        return "DEPARTMENT_QUERY"
    # Stat detection
    if any(s in q for s in STAT_SIGNALS) or any(s in q for s in PERSON_SIGNALS):
        return "FACT_QUERY"
    # Fallback: known names
    if any(name in q for name in ["yogesh", "saqlin", "mustaq", "vimal", "santhosh", "weslin", "ramanathan"]):
        return "PERSON_QUERY"
    # Continuation detection
    if q.strip() in ["yes", "no", "ok", "sure", "tell me more", "elaborate", "go on", "yup", "yeah", "okay"]:
        return "ELABORATION_QUERY"
    return "GENERAL_QUERY"

class RAGEngine:
    def __init__(self):
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            self.pc = Pinecone(api_key=pc_key)
            # v2: Primary msajce-v2, fallback to raglorin
            for idx_name in ["msajce-v2", "raglorin"]:
                try:
                    self.index = self.pc.Index(idx_name)
                    # Test connection
                    self.index.describe_index_stats()
                    logger.info(f"Connected to Pinecone index: {idx_name}")
                    break
                except: continue
            else: self.index = None
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
        base_dir = os.path.dirname(core_dir)

        # v2: Load bm25_index_v2 with fallback to bm25_index
        for bm25_dir_name in ["bm25_index_v2", "bm25_index"]:
            index_dir = os.path.join(base_dir, "data", bm25_dir_name)
            try:
                if os.path.exists(os.path.join(index_dir, "params.index.json")):
                    self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
                    logger.info(f"BM25 loaded from {bm25_dir_name}")
                    break
            except Exception as e:
                logger.error(f"BM25 Load Error ({bm25_dir_name}): {e}")
        else:
            self.bm25 = None

        self.vercel_gateway_url = "https://ai-gateway.vercel.sh/v1"
        self.openrouter_embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.generation_model = "google/gemini-2.0-flash-001"
        self.embedding_model = "openai/text-embedding-3-small"
        self.langfuse = Langfuse()

        # v2: Load ground_truth_v2 with fallback to ground_truth
        for gt_name in ["ground_truth_v2.json", "ground_truth.json"]:
            gt_path = os.path.join(base_dir, "data", gt_name)
            if os.path.exists(gt_path):
                self.ground_truth_path = gt_path
                break
        self.ground_truth = self._load_ground_truth()

    def _load_ground_truth(self):
        if os.path.exists(self.ground_truth_path):
            try:
                with open(self.ground_truth_path, 'r') as f:
                    data = json.load(f)
                # Verify expiry
                now = datetime.now()
                fresh_data = {}
                # Case-insensitive mapping for easier access
                for key, fact in data.items():
                    expiry_str = fact.get("valid_until", "2099-12-31")
                    expiry = datetime.strptime(expiry_str, "%Y-%m-%d")
                    if now < expiry:
                        val = fact.get("value")
                        fresh_data[key.lower()] = val
                        # Also add common names as keys for direct matching
                        if "president" in key.lower(): fresh_data["president"] = val
                        if "yogesh" in str(val).lower(): fresh_data["yogesh"] = val
                        if "ramanathan" in str(val).lower(): fresh_data["ramanathan"] = val
                return fresh_data
            except Exception as e:
                logger.error(f"Error loading ground truth: {e}")
        return {}

    def _safe_json_parse(self, text):
        try: return json.loads(text.strip())
        except:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try: return json.loads(match.group())
                except: pass
        return None

    def rrf_merge(self, semantic_hits: list, keyword_hits: list, k: int = 60) -> list:
        """Robust Reciprocal Rank Fusion (RRF)."""
        scores = {} # id -> RRF score
        all_hits = {} # id -> full hit object
        
        # 1. Process Semantic
        for rank, hit in enumerate(semantic_hits):
            h_id = hit["id"]
            all_hits[h_id] = hit
            scores[h_id] = scores.get(h_id, 0) + 1.0 / (k + rank)
            
        # 2. Process Keyword
        for rank, hit in enumerate(keyword_hits):
            h_id = hit["id"]
            if h_id not in all_hits: all_hits[h_id] = hit
            scores[h_id] = scores.get(h_id, 0) + 1.0 / (k + rank)
            
        # 3. Sort by RRF score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for h_id in sorted_ids:
            hit = all_hits[h_id]
            hit["rrf_score"] = scores[h_id]
            results.append(hit)
        return results

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
        
    def extract_entities(self, query: str) -> list:
        """Systematic Entity Extraction for institutional facts."""
        entities = []
        lower_q = query.lower()
        # Common entity categories across the college
        keywords = ["csi", "ieee", "sae", "iete", "ishrae", "nss", "yrc", "rotaract", "bus", "route", "scholarship", "faculty", "placement"]
        for k in keywords:
            if k in lower_q: entities.append(k)
        
        # Regex for potential names (Capitalized words)
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entities.extend([n.lower() for n in names])
        return list(set(entities))

    @traceable(name="Hybrid Retrieval")
    async def get_context(self, queries: list, trace, depth: int = 20):
        """Advanced Multi-Query Retrieval with RRF."""
        # 'queries' is now a list [original, alt1, alt2]
        all_semantic = []
        all_keyword = []
        
        # Build common filter once
        primary_q = queries[0]
        meta_filter = self.build_metadata_filter(primary_q)
        q_type = classify_query(primary_q)
        
        # SYSTEMATIC FIX: Dynamic Entity Extraction (Consolidated)
        entities = self.extract_entities(primary_q)

        async def fetch_one(q):
            p_hits = []
            b_hits = []
            try:
                # 1. Pinecone (Semantic) - Now using Vercel AI Gateway Pool
                top_k = depth
                emb = None
                
                # Try rotating Vercel Keys for Embedding
                vercel_keys = [
                    os.getenv("VERCEL_AI_KEY_6"),
                    os.getenv("VERCEL_AI_KEY_5"),
                    os.getenv("VERCEL_AI_KEY_7"),
                    os.getenv("AI_GATEWAY_API_KEY")
                ]
                
                async with httpx.AsyncClient() as client:
                    for k in vercel_keys:
                        if not k: continue
                        try:
                            headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                            url = "https://ai-gateway.vercel.sh/v1/embeddings"
                            e_res = await client.post(url, headers=headers, 
                                                     json={"model": self.embedding_model, "input": q}, timeout=5.0)
                            if e_res.status_code == 200:
                                emb = e_res.json()["data"][0]["embedding"]
                                break
                        except: continue

                # 2. BM25 (Keyword) - Parallel to Pinecone if possible, but here sequential for simplicity
                if self.bm25:
                    q_clean = re.sub(r'[^\w\s]', '', q.lower())
                    tokens = bm25s.tokenize(q_clean, stemmer=self.stemmer, show_progress=False)
                    chunks, scores = self.bm25.retrieve(tokens, k=15, show_progress=False)
                    for c, s in zip(chunks[0], scores[0]):
                        if isinstance(c, dict):
                            b_hits.append({"text": c.get("text", ""), "score": float(s), "id": c.get("chunk_id", ""), "metadata": c.get("metadata", {})})
                        else:
                            b_hits.append({"text": str(c), "score": float(s), "id": hashlib.md5(str(c).encode()).hexdigest()[:10], "metadata": {}})

                if emb and self.index:
                    p_res = self.index.query(vector=[float(x) for x in emb], top_k=top_k, filter=meta_filter, include_metadata=True)
                    p_hits = [{"text": m["metadata"]["text"], "score": m["score"], "id": m["id"], "metadata": m["metadata"]} for m in p_res["matches"]]
                
                return p_hits, b_hits
            except Exception as e:
                print(f"    [FETCH ERROR] {e}")
                return [], []

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
            h["f_score"] = h.get("rrf_score", 0.01) * priority_map.get(h["metadata"].get("priority", "medium"), 1.0)
            for key, val in h["metadata"].items():
                if key.startswith("entity_") and str(val).lower() in q_lower:
                    h["f_score"] *= 1.4
                elif key == "entities" and str(val).lower() in q_lower:
                    h["f_score"] *= 1.4

        # Final Sort
        results = sorted(merged, key=lambda x: x.get("f_score", 1.0), reverse=True)
        if not results: return []

        texts = [r["text"] for r in results[:20]]
        
        # AUDIT FIX: Re-ranker Fallback
        reranked = None
        try:
            if self.co:
                loop = asyncio.get_event_loop()
                rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=primary_q, documents=texts, top_n=10))
                reranked = [results[r.index] for r in rerank.results]
        except: pass
            
        if not reranked:
            try:
                context_summary = "\n".join([f"[{i}] {r.get('text', '')[:3000]}" for i, r in enumerate(results[:20])])
                rerank_prompt = {
                    "model": "google/gemini-2.0-flash-exp:free",
                    "messages": [
                        {"role": "system", "content": "Pick the indices [0, 1, 2...] of the chunks that BEST contain the answer to the user query. Return only a comma-separated list of numbers. If none match, return 'none'."},
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
            except: pass

        if not reranked or len(reranked) == 0:
            reranked = results[:10]

        top_score = reranked[0].get("f_score", 0) if reranked else 0
        for r in reranked:
            r["confidence_low"] = (top_score < 0.3)
        return reranked

    def extract_entities(self, query: str) -> list:
        """Systematic Entity Extraction for institutional facts."""
        entities = []
        lower_q = query.lower()
        keywords = ["csi", "ieee", "sae", "iete", "ishrae", "nss", "yrc", "rotaract", "bus", "route", "scholarship", "faculty", "placement"]
        for k in keywords:
            if k in lower_q: entities.append(k)
        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        entities.extend([n.lower() for n in names])
        return list(set(entities))

    def _post_process(self, text: str) -> str:
        """Strict aesthetic hardening (Master Rule Section 3)."""
        # Strip literal 'Blank Line' or '[Blank Line]' hallucinations
        text = re.sub(r'(?i)\bblank\s+line\b', '', text)
        text = re.sub(r'\[.*?\]', '', text) # Strip bracketed instructions
        
        text = re.sub(r'^#+.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[ \t]*[*+-][ \t]+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    async def query_stream(self, user_query, history=None, user_level="student", thinking=False):
        start_time = time.time()
        search_depth = 50 if thinking else 20
        top_n_rerank = 15 if thinking else 8
        trace = self.langfuse.trace(name="Lorin Enterprise RAG", input=user_query)
        
        persona_rules = "LANGUAGE LEVEL: Accessible & Friendly. Explain institutional jargon simply. Be guiding and helpful like an advisor."
        if user_level == "faculty":
            persona_rules = "LANGUAGE LEVEL: Professional & Technical. Use formal academic terminology. Be concise and authoritative."
        elif user_level == "admin":
            persona_rules = "LANGUAGE LEVEL: Executive & Formal. Prioritize data, percentages, and strategic institutional outcomes. High-density information."

        p = None
        # v2: Topic Anchoring for short continuations (fixes 'yes' hijacking)
        intent = classify_query(user_query)
        queries = [user_query]
        
        # [CRITICAL] Manual Identity Catch for Production Integrity
        if "yogesh" in user_query.lower():
            yield "Yogesh R is the President of the Computer Society of India (CSI) student chapter at MSAJCE. He is from the IT department (Batch 2022-2026)."
            return
        if "ramanathan" in user_query.lower() or "who built you" in user_query.lower():
            yield "I was developed by Ramanathan S (Ram), the Lead AI Architect at MSAJCE. He has built several high-performance systems including me (Lorin AI), Zenify, Zenpay, Pocket Lawyer, and Formora."
            return

        if intent == "ELABORATION_QUERY" and history:
            # Extract last assistant message to anchor retrieval
            last_lines = history.split("\n")
            anchor = ""
            for line in reversed(last_lines):
                if line.startswith("assistant:") or line.startswith("Lorin:"):
                    anchor = line.replace("assistant:", "").replace("Lorin:", "").strip()[:100]
                    break
            if anchor:
                queries.append(f"{anchor} {user_query}")
                print(f"    [ANCHORING] Query augmented with: {anchor}")
        intent = "FACTUAL"
        
        stop_words = ["bro", "sir", "please", "kindly", "tell", "show", "list", "give", "me", "all", "the"]
        is_greeting = len(user_query.split()) < 3 and any(w in user_query.lower() for w in ["hi", "hello", "hey", "yo"])
        if is_greeting: intent = "GREETING"
        
        if not is_greeting:
            gt_context = "\n".join([f"- {k.upper()}: {v}" for k, v in self.ground_truth.items()])
            data_pre = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [
                    {"role": "system", "content": f"""Classify intent and generate 2 search variations.
    Analyze HISTORY for pronoun resolution.
    GROUND TRUTH (STRICT):
    {gt_context}
    STRICT RULES:
    1. If the query is a follow-up (e.g. "list all", "show more", "who is he"), you MUST resolve pronouns using HISTORY.
    2. If the query is about an item EXPLICITLY in GROUND TRUTH, put it in 'direct_response'.
    Return JSON: {{category, search_query, alternative_queries: [q1, q2], direct_response}}
    """}, 
                    {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
                ]
            }
            pre_res = ""
            try:
                async for chunk in self._safe_vercel_request(data_pre):
                    pre_res += chunk
                p = self._safe_json_parse(pre_res)
                if p:
                    if p.get("direct_response"):
                        # If ground truth has a match for this name/key, use it
                        for k, v in self.ground_truth.items():
                            if k in user_query.lower():
                                yield v; return
                        yield p.get("direct_response"); return
                    intent = p.get("category", "FACTUAL")
            except: pass

        admin_keywords = ["document", "certificate", "marksheet", "fee", "admission process", "carry"]
        if any(k in user_query.lower() for k in admin_keywords):
            search_depth = 50

        # 2. Advanced Multi-Query Context Retrieval
        context_chunks = await self.get_context(queries, trace, depth=search_depth)
        
        if context_chunks and context_chunks[0].get("confidence_low"):
            if intent == "Identity" and "who" not in user_query.lower():
                yield "I do not have specific information on that institutional detail. Please check the college website or contact the administration directly."
                return
        
        if self.bm25:
            try:
                entities = self.extract_entities(user_query)
                boosted_chunks = []
                boost_terms = entities + [k for k in admin_keywords if k in user_query.lower()]
                for chunk in self.bm25.corpus:
                    match_score = 0
                    c_text = str(chunk.get("text", "")).lower()
                    c_title = str(chunk.get("page_title", "")).lower()
                    
                    for term in boost_terms:
                        if term in c_text: match_score += 1
                        if term in c_title: match_score += 3 # High weight for administrative titles
                    
                    if match_score >= 1: 
                        boosted_chunks.append((chunk, match_score))
                
                # Sort by match score and insert top 8 for higher institutional visibility
                boosted_chunks.sort(key=lambda x: x[1], reverse=True)
                for chunk, score in reversed(boosted_chunks[:8]):
                    context_chunks.insert(0, chunk)
            except Exception as e:
                pass
        
        # Cleanup encoding artifacts and non-printable chars for LLM clarity
        def clean_text(t):
            t = re.sub(r'[^\x00-\x7F]+', ' ', t)
            return t.replace('  ', ' ').strip()
 
        # Dynamic context length based on thinking mode
        context_text = "\n\n".join([f"[Source {i+1}]: {clean_text(c['text'])}" for i, c in enumerate(context_chunks[:top_n_rerank])])

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

{persona_rules}

RULES (follow strictly):
{greeting_rule}
2. FRIENDLY EXPLAINER: Always start with a 1-2 sentence narrative explanation or a warm introduction. Explain institutional jargon simply. Never just output a raw list without a helpful preamble. Deliver answers in clear, accessible English as a fluid narrative. Speak like a helpful advisor who explains things simply.
3. ZERO TABLES: Never use tables or complex grid structures. Telegram cannot render them. Use paragraphs and bullets instead.
4. SURGICAL BULLETS: Use center dots (•) for all lists of 3+ items, especially for bus routes, boarding points, and department names.
5. LEAD ARCHITECT: If asked about your developer, proudly state you were developed by **Ramanathan S** (Ram), the lead architect at MSAJCE.
6. LENGTH CONSTRAINT: 80-250 words to allow for detailed lists when needed, but keep general answers concise.
7. End every reply with one short, relevant follow-up question that invites the user to explore more facts (e.g., "Would you like to know about our scholarships or the transport routes?").
8. {"COUNT MODE: Provide a summary and total count only." if is_count_only else ""}
9. COURSE QUERIES: If a user asks about available courses or programs, ALWAYS list all 12 departments as the primary answer.

10. NO PARA-LISTS: For lists of people/faculty and their achievements, you MUST use a multi-line nested format with CLEAR SPACING between different individuals.
    *   Main Bullet (•): **Full Name**
    *   Sub-Bullet (-): Specific Achievement or Detail (on a new line below the name).
    *   **Double Space**: Always leave a double newline (press Enter twice) before starting the next person.
    CRITICAL: Never write the words 'Blank Line'. Just leave the actual physical space. Ensure clear visual separation between blocks.

11. OFFICE BEARERS: If asked for 'Office Bearers', you MUST distinguish between 'Nomination Authority' (Principal/Professors) and 'Student Office Bearers' (President/Vice President). List the Students first as they are the active student-facing leaders.
12. ENTITY DEDUPLICATION: If the context contains multiple entries that clearly refer to the same person, merge them.
13. FEE TRANSPARENCY: When stating any fees (Tuition, Transport, Hostel), you MUST explicitly mention that these are "approximate/tentative" and subject to final confirmation by the administration.

14. SURGICAL FOCUS: If a user asks for a specific individual (e.g., "Who is Yogesh?") or a specific role (e.g., "Who is the CSI President?"), you MUST provide only that specific person's details. NEVER list the entire committee, faculty group, or department members unless the user explicitly asks for a "list" or "all members".
15. CONFIDENT EXTRACTION: If you find any info (even a single sentence) about a person or topic in the context, state it as a definitive fact. NEVER apologize for having "limited" or "no more" information.
17. CONVERSATIONAL ANCHORING: If the user says "yes", "tell me more", or "sure", you MUST continue the previous topic. Do not switch to a new institutional fact (like CSI or Bus routes) unless the user specifically mentions a new topic.
18. STAY SURGICAL: Answer only what is asked. Do not dump entire lists if the user is following up on a specific person.

TONE: Helpful, professional, and narrative-driven. Connect facts with natural transitions.

[PRIORITY OVERRIDE]: If a fact exists in GROUND TRUTH, you MUST use it as the absolute truth. NEVER say "I don't have info" for items listed in GROUND TRUTH, even if the provided CONTEXT is empty or contradictory.

GROUND TRUTH (Institutional Memory):
• NAAC Accreditation: A+ Grade, Valid up to January 30, 2028.
• Total Departments: 12. You MUST list all 12 if asked: Civil, CSE, ECE, EEE, Mechanical, IT, AI&DS, CSBS, Cyber Security, AI&ML, VLSI, and ACT.
• NBA Accredited Departments: CSE, ECE, EEE, and Mechanical Engineering.
• Tuition Fees (Approximate): Rs. 75,000 for TNEA Counselling; Rs. 1,20,000 for Management Quota (Tentative).
• Hostel Fees (Approximate): Rs. 70,000 to Rs. 1,00,000 (Varies by sharing).
• Transport Fees (Approximate): Starting from Rs. 7,000 up to Rs. 49,000 max (Tentative, based on distance).
• Bus Rate Details: Approx. Rs. 1,200 to Rs. 1,700 per km.
• Highest Salary (2024 Batch): Rs. 12 Lakhs Per Annum (LPA).
• Top Recruiters: Fidelity National Financial, Intel, Amazon, Zoho, TCS, and CTS.
• Admission Code: 1301. AI&ML Seats: 30 (15 Management, 15 Government).
• Admission Documents Required: 10th & 12th Marks Sheets (Original), Transfer Certificate (TC), Community Certificate, Nativity Certificate (if applicable), First Graduate Certificate (if applicable), TNEA Allotment Order, and 10 Passport size photos. 
• Physical Verification: Students MUST carry original documents along with at least 3 sets of photocopies for the admission process.
• Principal: Dr. K.S. Srinivasan.
• IT Department Head: Dr. Weslin D (Associate Professor).
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
            "sources": list(set([c.get("metadata", {}).get("source_file", "Institutional Intelligence Archive") for c in context_chunks])),
            "num_chunks": len(context_chunks),
            "latency_ms": int((end_time - start_time) * 1000),
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            }
        }
            
        trace.update(output=self._post_process(full_answer))

    async def _safe_vercel_request(self, data, stream=False):
        """Robust multi-provider request handler with instant fallback logic."""
        # AUDIT FIX: Clean data & remove decommissioned models (Problem 2)
        if "model" in data and "llama-3.3" in data["model"]:
            data["model"] = "google/gemini-2.0-flash-001"
            
        # Prioritized Pool
        vercel_keys = [
            os.getenv("VERCEL_API_KEY_3"), 
            os.getenv("VERCEL_AI_KEY_5"), 
            os.getenv("VERCEL_AI_KEY_6"),
            os.getenv("AI_GATEWAY_API_KEY")
        ]
        google_key = os.getenv("GEMINI_API_KEY")
        
        # 1. TRY VERCEL POOL FIRST
        for k in vercel_keys:
            if not k: continue
            try:
                headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                url = f"https://ai-gateway.vercel.sh/v1/chat/completions"
                
                async with httpx.AsyncClient() as client:
                    if stream:
                        data["stream"] = True
                        async with client.stream("POST", url, headers=headers, json=data, timeout=30.0) as resp:
                            if resp.status_code in [200]:
                                async for line in resp.aiter_lines():
                                    if line.startswith("data: "):
                                        if "[DONE]" in line: break
                                        try:
                                            chunk = json.loads(line[6:])
                                            content = chunk["choices"][0]["delta"].get("content", "")
                                            if content: yield content
                                        except: pass
                                return # SUCCESS
                            else:
                                print(f"    [VERCEL FAIL] Key {k[:8]}... status {resp.status_code}")
                    else:
                        resp = await client.post(url, headers=headers, json=data, timeout=30.0)
                        if resp.status_code == 200:
                            content = resp.json()["choices"][0]["message"]["content"]
                            if content: yield content; return
            except Exception as e:
                print(f"    [VERCEL ERR] Key {k[:8]}... failed: {e}")

        # 2. EMERGENCY FALLBACK: DIRECT GOOGLE
        if google_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:streamGenerateContent?key={google_key}"
                # Convert OpenAI format to Google format
                msg_content = ""
                for m in data["messages"]: msg_content += f"{m['role']}: {m['content']}\n\n"
                
                payload = {
                    "contents": [{"parts": [{"text": msg_content}]}],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000}
                }
                
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", url, json=payload, timeout=30.0) as resp:
                        if resp.status_code == 200:
                            async for line in resp.aiter_lines():
                                try:
                                    chunk = json.loads(line)
                                    text = chunk[0]["candidates"][0]["content"]["parts"][0]["text"]
                                    if text: yield text
                                except: pass
                            return # SUCCESS
            except Exception as e:
                print(f"    [GOOGLE FALLBACK ERR] {e}")

        yield "The system is currently handling high traffic. Please try again in a few seconds."
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
