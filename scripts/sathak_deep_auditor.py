import asyncio
import os
import sys
import json
import time
import hashlib
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

# CONFIG
DATA_DIR = "d://.gemini/claude RAG/data/jsons"
AUDIT_DIR = "d://.gemini/claude RAG/data/audits/deep_audit"
QUESTIONS_PER_FILE = 15
BATCH_SIZE = 5 

os.makedirs(AUDIT_DIR, exist_ok=True)

async def generate_questions_for_file(file_path, engine):
    """Uses LLM to generate 30 specific questions from file content. Includes retries."""
    with open(file_path, "r") as f:
        data = json.load(f)
    
    # Combine chunks for context
    context = "\n".join([c.get("text", "") for c in data.get("chunks", [])])[:15000] 
    
    prompt = f"""You are a Forensic Auditor. Based ONLY on the institutional data below, generate {QUESTIONS_PER_FILE} brand new, highly specific questions that a student or parent might ask.
The questions must be fact-based (numbers, names, rules, dates).

DATA:
{context}

Format: Return a JSON array of strings only."""

    for attempt in range(3):
        res = ""
        try:
            # HYPER-DRIVE: Using Groq for near-instant generation
            async for chunk in engine._groq_request({"messages": [{"role": "user", "content": prompt}]}):
                res += chunk
            
            if res:
                cleaned = res.strip().replace("```json", "").replace("```", "")
                return json.loads(cleaned)
        except Exception as e:
            print(f"    [GEN WARN] Attempt {attempt+1} failed for {os.path.basename(file_path)}: {e}")
            await asyncio.sleep(10 * (attempt + 1))
            
    return []

async def evaluate_answer(query, response, source_text, engine):
    """Uses LLM to evaluate if the answer is accurate. Recognizes global institutional knowledge."""
    prompt = f"""Compare the BOT RESPONSE against the SOURCE TEXT and your general knowledge of the institution.
Is the bot response factually accurate? 

- If the info is in SOURCE TEXT and correct: PASS.
- If the info is NOT in SOURCE TEXT but is a known accurate institutional fact (Address, NBA, Principal name): PASS.
- If the info contradicts SOURCE TEXT: FAIL.
- If the bot says "I don't know" or refuses: FAIL.

QUERY: {query}
BOT RESPONSE: {response}
SOURCE TEXT: {source_text}

Return JSON: {{"status": "PASS" | "FAIL", "reason": "Brief explanation"}}"""

    res = ""
    # HYPER-DRIVE: Using Groq for near-instant evaluation
    async for chunk in engine._groq_request({"messages": [{"role": "user", "content": prompt}]}):
        res += chunk
    
    try:
        cleaned = res.strip().replace("```json", "").replace("```", "")
        return json.loads(cleaned)
    except:
        return {"status": "UNKNOWN", "reason": "Evaluation failed"}

async def audit_file(filename, engine):
    file_path = os.path.join(DATA_DIR, filename)
    print(f"--- AUDITING {filename} ---")
    
    # WARP OPTIMIZATION: Skip if already complete
    output_path = os.path.join(AUDIT_DIR, f"audit_{filename}")
    if os.path.exists(output_path):
        try:
            with open(output_path, "r") as f:
                if len(json.load(f)) >= QUESTIONS_PER_FILE:
                    print(f"  [WARP] {filename} already secured. Bypassing.")
                    return
        except: pass

    questions = await generate_questions_for_file(file_path, engine)
    if not questions: return
    
    # Get source text for evaluation
    with open(file_path, "r") as f:
        data = json.load(f)
    context = "\n".join([c.get("text", "") for c in data.get("chunks", [])])
    
    # RESUMPTION LOGIC: Load existing results if they exist
    output_path = os.path.join(AUDIT_DIR, f"audit_{filename}")
    results = []
    if os.path.exists(output_path):
        try:
            with open(output_path, "r") as f:
                results = json.load(f)
        except:
            results = []
            
    existing_questions = [r["question"] for r in results]

    for i, q in enumerate(questions, 1):
        if q in existing_questions:
            print(f"  [{i}/{len(questions)}] Skipping (Already audited): {q}")
            continue
            
        print(f"  [{i}/{len(questions)}] Q: {q}")
        ans = ""
        try:
            # APEX VELOCITY: 0.5s delay, powered by 3-Key Rotation
            await asyncio.sleep(0.5) 
            
            # RETRY WRAPPER FOR LLM CALLS
            for attempt in range(3):
                try:
                    async for chunk in engine.query_stream(q):
                        if isinstance(chunk, str):
                            ans += chunk
                    if ans: break
                except Exception as e:
                    print(f"    [BOT ERR] {e}. Retry {attempt+1}")
                    await asyncio.sleep(2)

            if not ans:
                print(f"    [WARN] No response after retries.")
            
            # EVALUATION DUEL
            eval_res = await evaluate_answer(q, ans, context, engine)
            
            results.append({
                "question": q,
                "answer": ans,
                "evaluation": eval_res
            })

            # Real-time Persistence
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            
            # LIVE LEDGER APPEND
            with open("d://.gemini/claude RAG/data/audits/live_audit_questions.txt", "a") as f:
                f.write(f"[{eval_res['status']}] {q}\n")
                
            print(f"  Result: {eval_res['status']}")
        except Exception as e:
            print(f"  Error on question {i}: {e}")
            
    print(f"FINISHED auditing {filename}.")

async def main():
    engine = RAGEngine()
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json")]
    
    # MAXIMUM OVERDRIVE: 6 parallel files for 20+ q/min
    semaphore = asyncio.Semaphore(6)
    
    async def semaphore_audit(file):
        async with semaphore:
            await audit_file(file, engine)
            
    tasks = [semaphore_audit(f) for f in files]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
