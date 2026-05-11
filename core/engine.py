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
DEPT_NAMES = ["cse", "it", "ece", "eee", "civil", "mech", "aids", "aiml", "cyber", "csbs", "sh", "vlsi"]
GREETING_SIGNALS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "how are you", "what's up", "namaste", "vanakkam"]
COMPLIMENT_SIGNALS = ["thanks", "thank you", "great", "awesome", "good job", "nice", "cool", "wow", "amazing", "well done", "perfect"]
CONTINUATION_SIGNALS = ["yes", "give", "need more", "ok give", "tell me more", "elaborate", "continue", "next", "more info", "go on", "him", "her", "it", "them", "about him", "about her", "about it"]

def classify_query(query: str) -> str:
    q = query.lower().strip()
    # Normalize common typos
    q = q.replace(" su ", " you ")
    
    # 1. GREETINGS & COMPLIMENTS (Immediate bypass)
    if any(s == q for s in GREETING_SIGNALS) or q in ["hi", "hello"]: return "GREETING"
    if any(s in q for s in COMPLIMENT_SIGNALS): return "COMPLIMENT"
    
    # 2. CONTEXTUAL PRONOUNS & CONTINUATIONS (High Priority for RAG history)
    # If the query contains "him", "her", "it", "them" or is a short confirmation
    pronouns = ["him", "her", "it", "them", "about him", "about her", "about it"]
    if any(p in q.split() for p in pronouns) or any(s == q or q.startswith(s) for s in CONTINUATION_SIGNALS) or q in ["yes", "no", "ok"]:
        return "ELABORATION_QUERY"

    # 3. SPECIFIC INTENTS
    if any(s in q for s in ROUTE_SIGNALS) or "ar8" in q or "ar " in q: return "ROUTE_QUERY"
    if any(s in q for s in ["who is", "tell me about", "hod", "principal", "yogesh", "ramanathan", "weslin"]): return "PERSON_QUERY"
    if any(s in q for s in ["admission", "apply", "enrol", "document"]): return "ADMISSION_QUERY"
    if any(s in q for s in RULE_SIGNALS): return "RULE_QUERY"
    if any(d in q for d in DEPT_NAMES) or "department" in q: return "DEPARTMENT_QUERY"
    if any(s in q for s in LIST_SIGNALS): return "LIST_QUERY"
    
    return "GENERAL_QUERY"

def clean_prose(text):
    """Converts markdown bullets and artifacts into fluid prose."""
    if not text: return ""
    text = re.sub(r'^[ \t]*[*+-][ \t]+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n+', ' ', text).strip()
    return text

def format_query_for_embedding(query: str, query_type: str, department: str = "") -> str:
    # Use a more descriptive natural language prompt for better vector alignment
    dept_info = f"in the {department} department" if department else "at MSAJCE"
    return f"Information about {query_type} {dept_info}: {query}"

class RAGEngine:
    def __init__(self):
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            self.pc = Pinecone(api_key=pc_key)
            # Primary index: final-secret-rag (1536-dim)
            try:
                self.index = self.pc.Index("final-secret-rag")
                self.index.describe_index_stats()
            except: self.index = None
            # Backup index: raglorin-backup (1536-dim)
            try:
                self.index_backup = self.pc.Index("raglorin-backup")
                self.index_backup.describe_index_stats()
            except: self.index_backup = None
            # GPT Master index: gpt-md-files (1536-dim)
            try:
                self.index_gpt = self.pc.Index("gpt-md-files")
                self.index_gpt.describe_index_stats()
            except: self.index_gpt = None
            
            # Claude Master index: claude-md-files (1536-dim)
            try:
                self.index_claude = self.pc.Index("claude-md-files")
                self.index_claude.describe_index_stats()
            except: self.index_claude = None
        except:
            self.index = None
            self.index_backup = None
            self.index_claude = None

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
                        val = str(fact.get("value"))
                        fresh_data[key.lower()] = val
                        
                        # AGGRESSIVE NAME INDEXING:
                        # Extract potential names from the value (Capitalized words)
                        # and map them back to this value.
                        names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', val)
                        for n in names:
                            fresh_data[n.lower()] = val
                            # Also map individual parts of the name if they are unique
                            parts = n.split()
                            if len(parts) > 1:
                                for p in parts:
                                    if len(p) > 3 and p.lower() not in ["the", "and", "prof", "doctor"]:
                                        # Only map if not already taken by a more specific key
                                        if p.lower() not in fresh_data:
                                            fresh_data[p.lower()] = val

                # INJECT MASTER DEPARTMENTS (12 UG + 2 PG + Ph.D)
                fresh_data["departments_list"] = "CSE (60), IT (60), ECE (60), AI&ML (60), EEE (30), Civil (30), Mech (30), AI&DS (30), CS&BS (30), Cyber Security (30), VLSI (30), ACT (30). PG: M.E.CSE (9), M.E.Structural (18). Ph.D: Mechanical."
                fresh_data["total_departments_count"] = "12 UG departments"

                # SAFETY NET PILLARS — Accurate values sourced from MD files
                fresh_data["college_basics"] = "MSAJCE (Mohamed Sathak A.J. College of Engineering). Address: 34, Rajiv Gandhi Salai (OMR), Siruseri IT Park, Siruseri, Chennai-603103. Established: 5th July 2001 by Mohamed Sathak Trust. Affiliated: Anna University Chennai. Approved: AICTE New Delhi. Campus: 70 acres. Code: 1301. Phone: +91 99400 04500. Email: msajce.office@gmail.com. Website: www.msajce-edu.in."
                fresh_data["sports_basics"] = "MSAJCE has 11 sports facilities: Basketball, Football, Cricket & Cricket Nets, Yoga, Kabaddi, Volleyball, Table Tennis, Carrom, Chess, Track and Field, Kho Kho. Fully equipped indoor Gymnasium. Sports quota admission for district/state/national level athletes. Annual trophies: Mohamed Sathak Trophy (Football), BSM Trophy (Cricket), Fit India Cyclothon. Director of Physical Education: Dr. K.P. Santhosh Nathan."
                fresh_data["placement_basics"] = "MSAJCE Placement Cell. Director: Dr. S. Vijay Ananth. Major recruiters: TCS, Infosys, CTS, Wipro, HCL, Zoho, Lenovo. 43+ MoUs with industries. Internship top companies 2022-23: Lenovo (75 students), Zoho (51), Green Valleys Shelters (45). Placement page: https://www.msajce-edu.in/placement.php."
                fresh_data["admission_basics"] = "Admissions via Government & Management Quota through TNEA Counselling. Apply: https://enrollonline.co.in/Registration/Apply/MSAJCE. Required documents: 10th & 12th Marksheets, Transfer Certificate, Community Certificate, TNEA Allotment Order. Head of Admissions: Dr. K.P. Santhosh Nathan (Ph: 9840886992). Principal: Dr. K.S. Srinivasan (Ph: 9150575066)."
                fresh_data["transport_basics"] = "MSAJCE operates 22 buses + 1 Tata ACE + 1 Ambulance. All buses arrive at college at 8:00AM. Routes: AR3-Uthiramerur (5:50AM), AR4-Moolakadai (6:10AM), AR5-MMDA School (6:15AM), AR6-ICF (6:15AM), AR7-Chunambedu (5:25AM, earliest), AR8-Manjambakkam (5:50AM), AR9-Ennore (6:15AM), AR10-Porur (6:25AM, latest), R22-Nemilichery (6:00AM). Transport Convener: Dr. K.P. Santhosh Nathan (Ph: 9840886992)."
                fresh_data["hostel_basics"] = "Boys Hostel: Inside campus, 3 blocks, 233 non-AC + 6 AC rooms, 2 persons/room, capacity 480 boys. Girls Hostel: Sholinganallur (5km from campus), 71 rooms, 3 persons/room, capacity 210 girls. Both have WiFi, LCD-TV, indoor games, reading room. Mess timings: Breakfast 7-8AM, Lunch 1-1:45PM, Dinner 7-8:30PM (working days)."
                fresh_data["facility_basics"] = "MSAJCE Learning Centre (Library): 8978 sq.ft, 29,853 volumes, 3,790 e-books, DELNET & J-Gate databases, Koha software, WiFi. Hours: Mon-Sat 8AM-7PM, Sun 10AM-4PM. Chief Librarian: Mr. S. Sudhakar. 15+ Engineering Labs. Cafeteria capacity 100 students, 8AM-8PM. Auditorium, Seminar Halls, Computer Centre."
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
                            
                            # Native 1536-dim to match raglorin/raglorin-backup indexes
                            e_res = await client.post("https://ai-gateway.vercel.sh/v1/embeddings", headers=headers, json={"model": self.embedding_model, "input": formatted_q}, timeout=5.0)
                            if e_res.status_code == 200:
                                emb = e_res.json()["data"][0]["embedding"]; break
                        except: continue

                # 1) BM25 keyword search (Fast)
                if self.bm25:
                    q_clean = re.sub(r'[^\w\s]', '', q.lower())
                    tokens = bm25s.tokenize(q_clean, stemmer=self.stemmer, show_progress=False)
                    chunks, scores = self.bm25.retrieve(tokens, k=8, show_progress=False)
                    for c, s in zip(chunks[0], scores[0]):
                        if isinstance(c, dict): b_hits.append({"text": c.get("text", ""), "score": float(s), "id": c.get("chunk_id", ""), "metadata": c.get("metadata", {})})
                
                if emb:
                    emb_floats = [float(x) for x in emb]
                    # 1) MASTER: final-secret-rag (Top Priority)
                    if self.index:
                        try:
                            m_res = self.index.query(vector=emb_floats, top_k=20, include_metadata=True)
                            for m in m_res["matches"]:
                                txt = m["metadata"].get("text", "")
                                if len(txt) < 30: continue
                                
                                # Master Multiplier (1.5x)
                                info_score = m["score"] * 1.5
                                p_hits.append({
                                    "text": txt, 
                                    "score": info_score, 
                                    "id": f"master_{m['id']}", 
                                    "metadata": m["metadata"]
                                })
                        except: pass
                    
                    # 2) SECONDARY: claude-md-files
                    if self.index_claude:
                        try:
                            c_res = self.index_claude.query(vector=emb_floats, top_k=15, include_metadata=True)
                            for m in c_res["matches"]:
                                txt = m["metadata"].get("text", "")
                                if len(txt) < 40: continue
                                
                                # Secondary Multiplier (1.2x)
                                info_score = m["score"] * 1.2
                                p_hits.append({
                                    "text": txt, 
                                    "score": info_score, 
                                    "id": f"secondary_{m['id']}", 
                                    "metadata": m["metadata"]
                                })
                        except: pass

                    # 3) BACKUP: gpt-md-files
                    if not p_hits and self.index_gpt:
                        try:
                            g_res = self.index_gpt.query(vector=emb_floats, top_k=15, include_metadata=True)
                            for m in g_res["matches"]:
                                txt = m["metadata"].get("text", "")
                                if len(txt) < 30: continue
                                
                                # Backup Multiplier (1.0x)
                                info_score = m["score"]
                                p_hits.append({
                                    "text": txt, 
                                    "score": info_score, 
                                    "id": f"backup_{m['id']}", 
                                    "metadata": m["metadata"]
                                })
                        except: pass
                return p_hits, b_hits
            except: return [], []

        results = await asyncio.gather(*[fetch_one(q) for q in queries])
        for p, b in results:
            all_semantic.extend(p); all_keyword.extend(b)

        merged = self.rrf_merge(all_semantic, all_keyword)
        
        # --- DEDUPLICATION LAYER ---
        seen_texts = set()
        deduped = []
        for h in merged:
            # Use a fingerprint (first 100 chars normalized) to detect duplicates
            fingerprint = re.sub(r'\W+', '', h["text"].lower())[:100]
            if fingerprint not in seen_texts:
                seen_texts.add(fingerprint)
                deduped.append(h)
        merged = deduped

        priority_map = {"critical": 2.0, "high": 1.6, "medium": 1.0, "low": 0.7}
        q_lower = primary_q.lower()
        
        # Determine target department for boosting
        target_dept = ""
        for d in DEPT_NAMES:
            if d in q_lower:
                target_dept = d
                break

        for h in merged:
            h["f_score"] = h.get("rrf_score", 0.01) * priority_map.get(h["metadata"].get("priority", "medium"), 1.0)
            
            # --- ROOT CAUSE FIX: Pillar & Department Boosting ---
            # 1. Surgical Dept Boost (3.0x)
            if target_dept and (target_dept in h["id"].lower() or target_dept in h["text"].lower()[:200]):
                h["f_score"] *= 3.0
            
            # 2. Pillar Boosting (2.5x) - Admissions, Placements, Sports, College, Transport, Hostel, Labs
            pillars = {
                "admission": ["admission", "quota", "seats", "intake", "fees", "eligibility", "apply"],
                "placement": ["placement", "company", "recruit", "package", "job", "salary", "hired"],
                "sports": ["sports", "game", "gym", "football", "cricket", "basketball", "trophy", "yoga"],
                "college": ["about", "located", "address", "code", "established", "vision", "mission"],
                "transport": ["bus", "route", "stop", "timing", "van", "ar8", "ar1", "ar2", "transport"],
                "hostel": ["hostel", "room", "mess", "warden", "accommodation", "stay", "dorm"],
                "faculty": ["hod", "professor", "staff", "faculty", "teacher", "head", "dean"],
                "facility": ["lab", "library", "canteen", "infrastructure", "auditorium", "seminar", "wifi"]
            }
            for pillar, keywords in pillars.items():
                if any(k in q_lower for k in keywords):
                    if any(k in h["text"].lower()[:500] for k in keywords):
                        h["f_score"] *= 2.5

            if any(str(val).lower() in q_lower for val in h["metadata"].values() if isinstance(val, (str, list))):
                h["f_score"] *= 1.4

        results = sorted(merged, key=lambda x: x.get("f_score", 1.0), reverse=True)
        if not results: return []
        # Increase rerank window to 20 non-junk candidates
        texts = [r["text"] for r in results[:20]] 
        reranked = None
        try:
            if self.co:
                # Use to_thread for synchronous Co.rerank to avoid loop issues
                rerank = await asyncio.to_thread(self.co.rerank, model="rerank-english-v3.0", query=primary_q, documents=texts, top_n=8)
                reranked = [results[r.index] for r in rerank.results]
        except: pass
        if not reranked: reranked = results[:8]
        return reranked

    def _post_process(self, text: str) -> str:
        text = re.sub(r'(?i)\bblank\s+line\b', '', text)
        text = re.sub(r'\[.*?\]', '', text) 
        text = re.sub(r'^#+.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^[ \t]*[*+-][ \t]+', '• ', text, flags=re.MULTILINE)
        # Aggressive HTML tag removal
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    async def query_stream(self, user_query, history=None, user_level="student", thinking=False):
        start_time = time.time()
        intent = classify_query(user_query)
        
        # 1. Conversational Bypass (Greetings & Compliments)
        if intent == "GREETING":
            resp = "Hello! I'm LORIN, your institutional AI for MSAJCE. How can I help you today?"
            yield resp
            yield {
                "type": "telemetry",
                "latency_ms": int((time.time() - start_time) * 1000),
                "tokens": 20,
                "intent": "GREETING",
                "sources": ["System Memory"]
            }
            return
            
        if intent == "COMPLIMENT":
            resp = "Thank you! I'm happy to help. Do you have any other questions about the college?"
            yield resp
            yield {
                "type": "telemetry",
                "latency_ms": int((time.time() - start_time) * 1000),
                "tokens": 20,
                "intent": "COMPLIMENT",
                "sources": ["System Memory"]
            }
            return

        queries = [user_query]
        if intent == "ELABORATION_QUERY" and history:
            last_lines = history.split("\n")
            # Look for the last bot response to anchor the context
            anchor = ""
            for l in reversed(last_lines):
                if "Bot:" in l or "assistant:" in l.lower():
                    anchor = l.split(":", 1)[1].strip()[:150]
                    break
            if anchor: queries.append(f"Regarding '{anchor}', {user_query}")

        # [HyDE & PRE-CLASSIFY]
        # SURGICAL CONTEXT: Only inject GT facts relevant to the query to save tokens (approx 50-70% savings)
        q_words = set(re.findall(r'\w+', user_query.lower()))
        relevant_gt = {}
        for k, v in self.ground_truth.items():
            if any(word in k.lower() or word in str(v).lower() for word in q_words if len(word) > 3):
                relevant_gt[k] = v
        
        # If no direct matches, include a small core set of safety pillars
        if not relevant_gt:
            pillars = ["principal", "college_code", "admission_contact", "address"]
            for p in pillars:
                if p in self.ground_truth: relevant_gt[p] = self.ground_truth[p]

        gt_context = "\n".join([f"- {k.upper()}: {v}" for k, v in relevant_gt.items()])
        
        pre_sys_prompt = f"""Classify intent and generate a 1-sentence 'Hypothetical Perfect Answer' (HyDE).
CONTEXTUAL RESOLUTION: If the user uses pronouns (him, her, it, they), resolve them using history.
GROUND TRUTH (Relevant Subset):
{gt_context}
Return JSON: {{category, search_query, hyde_answer, direct_response}}"""
        
        pre_messages = [{"role": "system", "content": pre_sys_prompt}]
        if history:
            for line in history.split("\n")[-4:]:
                if "User:" in line: pre_messages.append({"role": "user", "content": line.replace("User: ", "")})
                elif "Bot:" in line: pre_messages.append({"role": "assistant", "content": line.replace("Bot: ", "")})
        
        pre_messages.append({"role": "user", "content": user_query})

        data_pre = {
            "model": "google/gemini-2.0-flash-exp:free",
            "messages": pre_messages
        }
        pre_res = ""
        try:
            async for chunk in self._safe_vercel_request(data_pre): pre_res += chunk
            p = self._safe_json_parse(pre_res)
            if p:
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
                if p.get("search_query") and intent == "ELABORATION_QUERY":
                    queries.append(p.get("search_query"))
        except: pass

        context_chunks = await self.get_context(queries, None)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])
        sources = list(set([c['metadata'].get('page_title', c['metadata'].get('filename', 'Institutional Source')) for c in context_chunks]))

        system_prompt = f"""You are LORIN, the institutional AI for MSAJCE.
STRICT OPERATIONAL RULES:
1. GREETING BYPASS: DO NOT GREET THE USER. Start immediately.
2. DIRECT RESPONSE: Provide information IMMEDIATELY. No preamble.
3. ENTITY & PERSON RULES (CRITICAL):
   a) MULTIPLE MATCHES: If multiple people match the query (e.g., two people named 'Usha'), check their details carefully.
      - If they have DIFFERENT details (different dept, role), provide info for ALL of them.
      - If they have the SAME details, MERGE them into one response. DO NOT REPEAT IDENTICAL PROFILES.
   b) FULL DISCLOSURE: Provide EVERYTHING you have about the entity (name, dept, role, qualification, contact, highlights).
   c) Aim for a cohesive 80-100 word profile per person.
4. NARRATIVE FLOW: Write in fluid, natural paragraphs.
5. LISTS & COUNTING:
   a) Count items manually and provide the number in the first sentence.
   b) Use double newlines (\n\n) between list items.
6. FORMATTING: USE ONLY MARKDOWN. NO HTML TAGS (like <br>).
7. IDENTITY: You are LORIN, powered by Gemini 2.0 Flash.

GROUND TRUTH (Surgical):
{gt_context}

CONTEXT:
{context_text}"""

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
