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
        try:
            pc_key = os.getenv("PINECONE_API_KEY")
            if not pc_key: raise ValueError("Missing PINECONE_API_KEY")
            self.pc = Pinecone(api_key=pc_key)
            self.index = self.pc.Index("quickstart")
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
        span = trace.span(name="Retrieval", input={"query": query})
        
        # 1. Pinecone Vector Search
        pinecone_hits = []
        if self.index:
            try:
                async with httpx.AsyncClient() as client:
                    e_res = await client.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": self.embedding_model, "input": query}, timeout=30.0)
                    query_embedding = e_res.json()["data"][0]["embedding"]
                pinecone_hits = [m['metadata'] for m in self.index.query(vector=query_embedding, top_k=10, include_metadata=True)['matches']]
            except Exception as e:
                print(f"Lorin Engine: Pinecone Retrieval Error: {e}")

        # 2. BM25 Lexical Search
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
        
        # INCREASE DEPTH: Send more chunks to reranker
        if not combined: return []
        
        # 3. Reranking (Optional)
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
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query)
        
        # 1. Intent & Refinement
        span = trace.span(name="Pre-Processor")
        data = {
            "model": self.generation_model,
            "messages": [
                {"role": "system", "content": """Classify intent and rewrite for search. 
Return JSON: {category, search_query, direct_response}

CATEGORIES: 
- DEVELOPER: If asking about Ramanathan S, Ram, or the bot's creator/developer.
- GREETING: Hello, hi, etc.
- INSTITUTIONAL: Default search.

Return 'search_query' by preserving all technical terms, numbers (e.g. '1301', 'AR-3'), and entity names. NEVER over-simplify.
If asking for a 'code', 'number', 'contact', or 'accreditation/NAAC', include those words in the search_query.
STRICT RULE: Never tell the user to 'check the website' or 'refer to the portal' if the information might be in the context. Always provide a direct answer.

If category is DEVELOPER, set direct_response to:
"**Ramanathan S (Ram)** is the Lead AI Developer and System Architect at MSAJCE. He is a visionary 2nd-year B.Tech IT student who has engineered several high-performance AI and Fintech systems.\n\n*Connect with him here:*\n\n. [LinkedIn](https://linkedin.com/in/ramanathan-s)\n\n. [Portfolio](https://ram-ai-portfolio.vercel.app)\n\n. [Source Code (GitHub)](https://github.com/hackerstudent29/MSAJCE-LORIN.git)\n\n. Email: ramanathanb86@gmail.com\n\n*Major Projects:*\n\n. *Lorin RAG*: A sophisticated institutional intelligence engine.\n\n. *Zenpay*: A robust, enterprise-grade Fintech monorepo.\n\n. *Pocket Lawyer*: An AI legal-tech platform with Tamil support.\n\n. *Formora*: An AI-driven SaaS form builder.\n\n. *Smart Hostel & Event Management Systems*.\n\nIs there anything specific you would like to know about Ram's technical expertise or projects?"
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
   Example:
   . Item one.
   . Item two.
2. CLOSING: Always end every response with a friendly follow-up question. 
   - This question MUST be contextually related to the user's last query.
   - If no specific follow-up topic is clear, use: "Is there anything else I can help you with today?"
3. NO REDIRECTS: Never tell the user to 'check the website' if the information is available.
4. IDENTITY: If asked about 'Ramanathan', 'Ram', or 'the developer', speak in the THIRD PERSON (e.g., 'Ramanathan is...').
5. If you truly don't know the answer, say "I'm sorry, I don't have that specific info in my records yet. Is there anything else I can help you with?"

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
                "latency": latency_ms,
                "tokens": len(final_answer.split()) * 1.3,
                "status": "SUCCESS" if final_answer else "FAILED"
            }
            await self.redis.lpush("lorin_forensic_logs", json.dumps(log_entry))
            await self.redis.ltrim("lorin_forensic_logs", 0, 10000)
        except Exception as e:
            logger.error(f"Forensic Logging Error: {e}")

        return final_answer
