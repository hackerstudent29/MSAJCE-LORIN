import os
import json
import time
import hashlib
import re
import requests
import bm25s
import Stemmer
import cohere
import logging
from pinecone import Pinecone
from upstash_redis import Redis
from dotenv import load_dotenv
from langsmith import traceable
from langfuse import Langfuse

load_dotenv()
logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self):
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index("quickstart")
        self.co = cohere.ClientV2(os.getenv("COHERE_API_KEY"))
        self.redis = Redis(url=os.getenv("UPSTASH_REDIS_REST_URL"), token=os.getenv("UPSTASH_REDIS_REST_TOKEN"))
        self.stemmer = Stemmer.Stemmer("english")
        
        # Self-Healing BM25 Index
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        index_dir = os.path.join(base_dir, "data", "bm25_index")
        chunks_path = os.path.join(base_dir, "data", "unified_chunks.json")
        
        if os.path.exists(index_dir) and os.path.exists(os.path.join(index_dir, "params.index.json")):
            try:
                self.bm25 = bm25s.BM25.load(index_dir, load_corpus=True)
                print("Lorin Engine: Loaded existing BM25 index.")
            except Exception as e:
                print(f"Lorin Engine: Failed to load index, rebuilding... ({e})")
                self._rebuild_bm25(chunks_path, index_dir)
        else:
            print("Lorin Engine: Index missing, rebuilding from unified_chunks...")
            self._rebuild_bm25(chunks_path, index_dir)

        self.vercel_gateway_url = "https://ai-gateway.vercel.sh/v1"
        self.openrouter_embed_url = "https://openrouter.ai/api/v1/embeddings"
        self.generation_model = "openai/gpt-4o-mini"
        self.embedding_model = "openai/text-embedding-3-small"
        
        # Initialize Langfuse
        self.langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_BASE_URL")
        )

    def _rebuild_bm25(self, chunks_path, index_dir):
        """Rebuilds the BM25 index from raw JSON chunks."""
        with open(chunks_path, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        corpus = [c['text'] for c in chunks]
        tokens = bm25s.tokenize(corpus, stemmer=self.stemmer)
        
        self.bm25 = bm25s.BM25(corpus=chunks)
        self.bm25.index(tokens)
        
        # Create directory if missing
        os.makedirs(index_dir, exist_ok=True)
        self.bm25.save(index_dir, corpus=chunks)
        print(f"Lorin Engine: Successfully rebuilt BM25 index with {len(chunks)} chunks.")

    def _safe_vercel_request(self, data, label="Request", span=None):
        # Multi-key fallback for resilience on different hosting environments
        gateway_key = (
            os.getenv('VERCEL_AI_KEY_6') or 
            os.getenv('VERCEL_AI_KEY_5') or 
            os.getenv('AI_GATEWAY_API_KEY')
        )
        
        # Last resort: Scan environment for any Vercel Key
        if not gateway_key:
            for key, value in os.environ.items():
                if value.startswith("vck_"):
                    gateway_key = value
                    break

        if not gateway_key:
            return "Error: No Vercel AI Key (vck_*) found in environment. Checked: VERCEL_AI_KEY_6, VERCEL_AI_KEY_5, AI_GATEWAY_API_KEY."
            
        headers = {"Authorization": f"Bearer {gateway_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(f"{self.vercel_gateway_url}/chat/completions", headers=headers, json=data, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                if span:
                    span.event(name=f"LLM {label}", input=data, output=content, metadata={"usage": result.get("usage")})
                return content
            else:
                err_msg = f"Error {resp.status_code}: {resp.text}"
                logger.error(f"{label} failed: {err_msg}")
                return err_msg
        except Exception as e:
            logger.error(f"{label} exception: {e}")
            return str(e)

    # Unused unified_pre_process removed for cleanliness


    @traceable(name="Adaptive Retrieval")
    def get_context_v41(self, query, original_query, complexity, trace):
        span = trace.span(name="Retrieval", input={"query": query, "original_query": original_query, "complexity": complexity})
        
        # Embedding
        query_embedding = requests.post(self.openrouter_embed_url, headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"}, json={"model": self.embedding_model, "input": query}).json()["data"][0]["embedding"]
        
        # Increase top_n for more comprehensive context
        top_n = 10
        
        # 1. Pinecone Vector Search
        pinecone_chunks = [m['metadata'] for m in self.index.query(vector=query_embedding, top_k=top_n, include_metadata=True)['matches']]
        
        # BM25 Lexical Search
        bm25_hits = []
        try:
            query_tokens = bm25s.tokenize(query, stemmer=self.stemmer)
            bm25_chunks, bm25_scores = self.bm25.retrieve(query_tokens, k=15)
            bm25_hits = bm25_chunks[0].tolist()
        except Exception as e:
            print(f"DEBUG: BM25 Retrieval failed: {e}")
            bm25_hits = []
        
        # 2.5. Exact Keyword Fallback (Proper Noun / Rare Word Protection)
        exact_hits = []
        try:
            words = set(re.findall(r'\b\w{4,}\b', query.lower() + " " + original_query.lower()))
            stop_words = {'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how', 'many', 'much', 'chose', 'choosed', 'students', 'university', 'college', 'department', 'engineering', 'about', 'their', 'give', 'want', 'know'}
            rare_words = [w for w in words if w not in stop_words]
            
            for w in rare_words:
                matches = [c for c in self.bm25.corpus if w in c.get('text', '').lower()]
                if 0 < len(matches) <= 8: 
                    exact_hits.extend(matches)
        except Exception as e:
            print(f"DEBUG: Exact Fallback failed: {e}")
            
        combined = []
        seen = set()
        for c in exact_hits + pinecone_chunks + bm25_hits:
            if c['chunk_id'] not in seen:
                combined.append(c); seen.add(c['chunk_id'])
        
        if not combined: 
            span.end(output="NO_RESULTS")
            return [], 0
            
        # Rerank
        texts = [c['text'] for c in combined]
        rerank = self.co.rerank(model="rerank-english-v3.0", query=query, documents=texts, top_n=top_n)
        
        results = [combined[r.index] for r in rerank.results]
        max_score = rerank.results[0].relevance_score if rerank.results else 0
        
        span.end(output={"num_results": len(results), "max_score": max_score})
        return results, max_score

    @traceable(name="Balanced Generator")
    def _safe_json_parse(self, text):
        try:
            # First attempt: direct parse
            return json.loads(text.strip())
        except:
            # Second attempt: find JSON block
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except:
                    pass
            # Third attempt: strip markdown
            clean_res = text.strip()
            if clean_res.startswith("```"):
                lines = clean_res.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_res = "\n".join(lines).strip()
                try:
                    return json.loads(clean_res)
                except:
                    return None
            return None

    def generate_balanced(self, query, context, trace):
        span = trace.span(name="Generation", input={"query": query})
        system_prompt = (
            "### LORIN MASTER PROTOCOL v5.0 ###\n"
            "\n"
            "PILLAR 1: DATA FIDELITY (STRICT GROUNDING)\n"
            "• Use ONLY the provided context. \n"
            "• NO HALLUCINATIONS: If a specific name/role is not in context, say 'I couldn't find [Name] in my current records'—NEVER guess or provide a similar name.\n"
            "• EXACT MATCHING: If the user asks for '2023 Batch', only provide 2023 data. If they ask for 'IT', only provide IT data.\n"
            "\n"
            "PILLAR 2: STRUCTURAL INTEGRITY (VERTICAL LISTING)\n"
            "• PURE PLAIN TEXT: No bold (**), no headers (###), no underscores (_).\n"
            "• LIST MANDATE: Any response containing more than 1 item (names, steps, criteria) MUST use a vertical bullet list.\n"
            "• FORMAT: • [Item Content] (One per line).\n"
            "\n"
            "PILLAR 3: ADAPTIVE ACADEMIC CALENDAR (2026)\n"
            "• 1st Year: 2025-2029 | 2nd Year: 2024-2028 | 3rd Year: 2023-2027 | 4th Year: 2022-2026\n"
            "• LOGIC: Map 'X year' queries to the batch above. However, if the user explicitly names a batch (e.g., '2023 batch'), prioritize that batch string over the year name.\n"
            "\n"
            "PILLAR 4: SCHOLARSHIP PROTOCOL\n"
            "• General: 1-line summary for all.\n"
            "• Specific: Full breakdown (Eligibility, Amount, Agency, Contact).\n"
            "\n"
            "PILLAR 5: PERSONA (THE COLLEGE BUDDY)\n"
            "• STYLE: Casual college buddy (B1 Level English). Use friendly, relatable phrasing (e.g., 'Cool, right?', 'Anything else?', 'Wanna know more?').\n"
            "• INTERACTIVE CLOSING: You MUST end every single response with a relevant follow-up question to keep the conversation going.\n"
            "• TONE: Helpful, enthusiastic, and grounded. Use 'I' and 'we'.\n"
            "\n"
            "PILLAR 6: PROFILE PRESENTATION (STAFF/PERSONNEL)\n"
            "• ORDER: Achievements (Patents, Books, Awards, Medals) -> Key Roles -> Experience/Background.\n"
            "• PHRASING: Use full descriptive sentences for roles. NEVER use comma labels like 'Principal, MSAJCE'. \n"
            "• EXAMPLE: 'He is the Principal of MSAJCE' or 'She serves as the Head of Department.'\n"
            "\n"
            "JSON SCHEMA: {\"confidence\": \"HIGH|MEDIUM|LOW\", \"answer\": \"your response here\"}"
        )
        prompt = f"CONTEXT:\n{context}\n\nQUESTION: {query}"
        data = {
            "model": self.generation_model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
            "max_tokens": 1000
        }
        res = self._safe_vercel_request(data, label="Generator", span=span)
        p = self._safe_json_parse(res)
        if p:
            ans_obj = p.get("answer", "")
            if isinstance(ans_obj, dict):
                # Format dict into a clean vertical list
                lines = []
                for k, v in ans_obj.items():
                    key_pretty = k.replace("_", " ").title()
                    if isinstance(v, list):
                        lines.append(f"{key_pretty}:")
                        for item in v:
                            if isinstance(item, dict):
                                # Format nested dicts as one-line summaries
                                item_str = ", ".join([f"{sk}: {sv}" for sk, sv in item.items()])
                                lines.append(f"• {item_str}")
                            else:
                                lines.append(f"• {item}")
                    else:
                        lines.append(f"{key_pretty}: {v}")
                ans = "\n".join(lines)
            else:
                ans = str(ans_obj)
            
            ans = ans.strip()
            # Strict cleaning: Remove any remaining markdown markers
            ans = re.sub(r'[\*#_]', '', ans)
            # Ensure bullets are dots and ALWAYS start on a new line (avoiding hyphenated words)
            ans = re.sub(r'([^\n])\s+[•\-\*]\s+', r'\1\n• ', ans)
            ans = re.sub(r'^\s*[•\-\*]\s*', '• ', ans, flags=re.MULTILINE)
            span.end(output={"confidence": p.get("confidence"), "answer_length": len(ans)})
            return p.get("confidence"), ans
        else:
            span.end(error="JSON_PARSE_ERROR")
            # Fallback: try to see if the response itself was the answer
            if len(res) > 20 and "{" not in res:
                 return "MEDIUM", res
            return "LOW", "I'm having a little trouble parsing the records. Can you try asking differently?"

    def query(self, user_query, history=None):
        # Initialize Langfuse Trace
        trace = self.langfuse.trace(name="Lorin RAG Query", input=user_query, metadata={"has_history": bool(history)})
        
        # 1. Identity Fast-Pass & Query Refinement
        lower_q = user_query.lower()
        
        # Unified Router & Intent Classification
        span = trace.span(name="Pre-Processor", input={"query": user_query})
        
        system_prompt = (
            "You are the Intent Classifier and Query Optimizer for MSAJCE (Lorin).\n"
            "CATEGORIES:\n"
            "- GREETING: 'hi', 'hey', 'hello', 'thanks', etc.\n"
            "- NON_INSTITUTIONAL: Politics, sports, or other colleges.\n"
            "- INSTITUTIONAL: Queries about MSAJCE institutional data.\n"
            "\n"
            "RULES:\n"
            "1. If the query mentions a name (Usha, Srinivasan, Principal, etc.), ALWAYS set category to 'INSTITUTIONAL'.\n"
            "2. FOLLOW-UP & PRONOUN RESOLUTION: If the query is short ('Yes', 'Sure', 'Tell me') OR contains pronouns ('him', 'her', 'it', 'them'), LOOK AT THE HISTORY. Rewrite the query to include the actual subject name or topic.\n"
            "   - AMBIGUITY RULE: If multiple people were mentioned, ALWAYS prioritize the person from the MOST RECENT exchange (the very last Bot/User turn).\n"
            "   - Example: User asked 'Who is Weslin?', then 'Who is Srinivasan?', then 'Tell me about him' -> search_query: 'Dr. K.S. Srinivasan'.\n"
            "3. search_query: Formal rewrite for institutional search. For people, use just their name.\n"
            "4. SPELLING CORRECTION: Fix typos in search_query.\n"
            "Return ONLY a RAW JSON object with: 'category', 'search_query', 'direct_response'."
        )
        msg = f"HISTORY:\n{history}\n\nQUERY: {user_query}"
        data = {
            "model": self.generation_model,
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": msg}],
            "max_tokens": 200
        }
        res = self._safe_vercel_request(data, label="Pre-Processor", span=span)
        print(f"DEBUG: Pre-Processor RAW Response: {res}")
        p = self._safe_json_parse(res)
        
        if p:
            category = p.get("category")
            direct_resp = p.get("direct_response")
            search_query = p.get("search_query")
            if not search_query or not search_query.strip():
                search_query = user_query
            
            # Special Gate: If we see institutional markers, force it
            if any(x in lower_q for x in ["who is", "professor", "faculty", "usha", "srinivasan", "principal", "admission"]):
                category = "INSTITUTIONAL"

            if category == "GREETING" and direct_resp:
                span.end(output=p)
                trace.update(output=direct_resp)
                return direct_resp
            
            span.end(output=p)
        else:
            span.end(output="FALLBACK")
            category, search_query = "INSTITUTIONAL", user_query

        # 2. Adaptive Retrieval & Heuristic Gate
        relevant_chunks, max_score = self.get_context_v41(search_query, user_query, "SIMPLE", trace)

        # 3. Balanced Generation
        context_text = "\n\n".join([f"[Source {i+1}]: {c['text']}" for i, c in enumerate(relevant_chunks)])
        confidence, answer = self.generate_balanced(user_query, context_text, trace)
        
        # 4. Confidence Fallback
        final_answer = answer
        
        trace.update(output=final_answer)
        return final_answer
