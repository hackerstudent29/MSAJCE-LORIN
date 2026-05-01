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
            index_name = os.getenv("PINECONE_INDEX_NAME", "quickstart")
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
            test_path = os.path.join(root, "data", "unified_chunks.json")
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
        corpus = [c['text'] for c in chunks]
        tokens = bm25s.tokenize(corpus, stemmer=self.stemmer)
        self.bm25 = bm25s.BM25(corpus=chunks)
        self.bm25.index(tokens)
        os.makedirs(index_dir, exist_ok=True)
        self.bm25.save(index_dir, corpus=chunks)
        print(f"Lorin Engine: Successfully rebuilt BM25 index with {len(chunks)} chunks.")

    async def _safe_vercel_request(self, data, label="Request", span=None):
        # Scan for any Vercel AI Gateway key (vck_ or vcp_)
        gateway_key = os.getenv('VERCEL_AI_KEY_6') or os.getenv('VERCEL_AI_KEY_5') or os.getenv('AI_GATEWAY_API_KEY')
        
        if not gateway_key:
            for key, value in os.environ.items():
                # Support both legacy (vck_) and new (vcp_) Vercel keys
                if value and (value.startswith("vck_") or value.startswith("vcp_")):
                    gateway_key = value
                    break
        
        if not gateway_key: return f"Error: No AI Gateway Key (vck_/vcp_) found for {label}."
            
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
        """Parallelized RAG Retrieval (Pinecone + BM25)"""
        span = trace.span(name="Retrieval", input={"query": query})
        
        async def fetch_pinecone():
            if not self.index: return []
            try:
                async with httpx.AsyncClient() as client:
                    e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": self.embedding_model, "input": query}, timeout=10.0)
                    query_embedding = e_res.json()["data"][0]["embedding"]
                    
                    p_res = self.index.query(vector=query_embedding, top_k=10, include_metadata=True)
                    return [{"text": m["metadata"]["text"], "score": m["score"], "chunk_id": m["id"]} for m in p_res["matches"]]
            except Exception as e:
                print(f"Lorin Engine: Pinecone Error: {e}")
                return []

        async def fetch_bm25():
            if not self.bm25: return []
            try:
                tokens = bm25s.tokenize(query, stemmer=self.stemmer)
                chunks, _ = self.bm25.retrieve(tokens, k=10)
                return chunks[0].tolist()
            except Exception as e:
                print(f"Lorin Engine: BM25 Error: {e}")
                return []

        # RUN IN PARALLEL
        pinecone_task = fetch_pinecone()
        bm25_task = fetch_bm25()
        p_hits, b_hits = await asyncio.gather(pinecone_task, bm25_task)
        
        combined = []; seen = set()
        for c in p_hits + b_hits:
            cid = c.get('chunk_id') or c.get('id')
            if cid and cid not in seen:
                combined.append(c); seen.add(cid)
        
        print(f"Lorin Engine: Retrieval Hits -> Pinecone: {len(p_hits)}, BM25: {len(b_hits)}, Combined: {len(combined)}")
        
        # 3. Reranking (Optional)
        if not combined: return []
        texts = [c['text'] for c in combined]
        if self.co:
            try:
                loop = asyncio.get_event_loop()
                rerank = await loop.run_in_executor(None, lambda: self.co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=12))
                results = [combined[r.index] for r in rerank.results]
                span.end(output={"results": len(results)})
                return results
            except Exception as e:
                print(f"Lorin Engine: Rerank Error: {e}")
        
        # Return raw hits if reranker fails (Increased to 10 for better coverage)
        span.end(output={"results": len(combined[:10])})
        return combined[:10]

    async def query(self, user_query, history=None):
        start_time = time.time()
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        
        # 1. Intent & Refinement
        span = trace.span(name="Pre-Processor")
        data = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": """Classify intent and rewrite for search. 
Return JSON: {category, search_query, direct_response}

CATEGORIES: 
- DEVELOPER: ONLY if asking about Ramanathan S, Ram, or the specific bot creator/developer.
- GREETING: Hello, hi, etc.
- INSTITUTIONAL: Default for all college, faculty, department, bus, or admission questions. Search for names like 'Weslin' or 'Kannan' as 'Dr. Weslin D' or 'Dr. Kannan S'.

SEARCH REWRITING:
1. TYPO-PROOFING: If a name looks misspelled (e.g. 'Wesling' for 'Weslin'), use the CORRECTED version.
2. ENTITY FOCUS: Always include the full name and department (e.g. 'Dr. Weslin D MSAJCE Associate Professor') in the search_query.
3. RE-BALANCE: Treat faculty records as high-priority. If a name is mentioned, search for their specific role and patents.

If category is DEVELOPER, set direct_response to:
"**Ramanathan S (Ram)** is the Lead AI Developer and System Architect at MSAJCE. He is a visionary 2nd-year B.Tech IT student specializing in high-performance AI systems and Fintech architecture.\n\n*Connect with him here:*\n\n. [LinkedIn](https://linkedin.com/in/ramanathan-s)\n\n. [Portfolio](https://ram-ai-portfolio.vercel.app)\n\n. [Source Code (GitHub)](https://github.com/hackerstudent29/MSAJCE-LORIN.git)\n\n. Email: ramanathanb86@gmail.com\n\n*Major Engineering Projects:*\n\n. **Zenify**: High-performance music streaming (Next.js 14).\n\n. **Zenpay**: Production-grade Payment Gateway (Monorepo).\n\n. **Lorin RAG**: Institutional intelligence engine.\n\n. **Pocket Lawyer**: AI legal-assistant (Next.js 16).\n\n. **Formora**: AI-driven SaaS form builder.\n\n. **Smart Hostel & Event Systems**: Enterprise utility platforms.\n\nIs there anything specific you would like to know about Ram's technical expertise or architecture designs?"
"""}, 
                {"role": "user", "content": f"History: {history}\nQuery: {user_query}"}
            ],
            "max_tokens": 400
        }
        res = await self._safe_vercel_request(data, label="Pre-Processor", span=span)
        p = self._safe_json_parse(res)
        
        if p and p.get("direct_response"):
            return p.get("direct_response")
            
        search_query = p.get("search_query", user_query) if p else user_query

        # 2. Retrieval
        context_chunks = await self.get_context(search_query, trace)
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(context_chunks)])

        # 3. Generation
        gen_span = trace.span(name="Generation")
        # 4. Generate Final Answer
        system_prompt = f"""You are Lorin, the institutional assistant for MSAJCE (Mohamed Sathak A.J. College of Engineering).
Your tone is casual, friendly, and helpful (B1 level English). Use proper punctuation and always end with a full stop (.).

RULES:
1. BULLET POINTS: For any list or multiple items, you MUST use '. ' (one dot and a space) as the bullet point prefix.
2. VERTICAL LAYOUT: You MUST use double newlines (`\n\n`) between every bullet point to force a clean vertical list. NEVER use paragraph style for projects or links.
3. CLOSING: Always end every response with a friendly follow-up question. 
   - This question MUST be contextually related to the user's last query.
   - If no specific follow-up topic is clear, use: "Is there anything else I can help you with today?"
4. NO REDIRECTS: Never tell the user to 'check the website' if the information is available.
5. IDENTITY: If asked about 'Ramanathan', 'Ram', or 'the developer', speak in the THIRD PERSON (e.g., 'Ramanathan is...').
6. If you truly don't know the answer, say "I'm sorry, I don't have that specific info in my records yet. Is there anything else I can help you with?"

CONTEXT:
{context_text}

Conversation History:
{history if history else "No previous history."}"""
        data_gen = {
            "model": self.generation_model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Query: {user_query}"}],
            "max_tokens": 800
        }
        res_gen = await self._safe_vercel_request(data_gen, label="Generator", span=gen_span)
        
        final_answer = res_gen
        trace.update(output=final_answer)

        # --- Sunday Intelligence: Forensic Logging ---
        try:
            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": trace.trace_id if hasattr(trace, 'trace_id') else "sess_" + str(int(time.time())),
                "query": user_query,
                "category": p.get("category", "GENERAL") if p else "ERROR",
                "score": max([float(c.get('score', 0)) for c in context_chunks]) if context_chunks else 0.0,
                "hits_pinecone": len([c for c in context_chunks if 'score' in c]), # Approximate
                "hits_bm25": len([c for c in context_chunks if 'score' not in c]),
                "latency": latency_ms,
                "tokens": len(final_answer.split()) * 1.3,
                "status": "SUCCESS" if final_answer else "FAILED"
            }
            await self.redis.lpush("lorin_forensic_logs", json.dumps(log_entry))
            await self.redis.ltrim("lorin_forensic_logs", 0, 10000)
        except Exception as e:
            print(f"Forensic Logging Error: {e}")

        return final_answer
