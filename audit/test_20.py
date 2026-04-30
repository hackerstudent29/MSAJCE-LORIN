import os
import time
import json
from engine import RAGEngine

def run_20_questions_test():
    engine = RAGEngine()
    
    questions = [
        "What are the hostel rules for boys?",
        "Tell me about the incubation center facilities.",
        "How can I register on the alumni portal?",
        "What are the transport routes available?",
        "Which clubs are active for engineering students?",
        "What was the placement record for the last batch?",
        "Is there a gym facility in the hostel?",
        "How does the incubation center support startups?",
        "What are the girls' hostel entry timings?",
        "List the bus routes for the Tambaram area.",
        "Tell me about the GDSC club.",
        "What are the mess timings for breakfast and dinner?",
        "Who are the top recruiters for this year?",
        "Can alumni mentor current students?",
        "What are the transport fees for this semester?",
        "Is there a robotics club in the college?",
        "What are the rules for using the common room in the hostel?",
        "What is the contact for the placement officer?",
        "Are there any coding competitions organized by clubs?",
        "How can I apply for transport facilities?"
    ]

    print(f"--- STARTING HARDENED 20-QUESTION AUDIT ---")
    results = []
    success_count = 0
    
    for i, q in enumerate(questions):
        print(f"[{i+1}/20] Querying: {q}")
        start_time = time.time()
        
        try:
            answer = engine.query(q, user_id="audit_tester_v2")
            latency = time.time() - start_time
            
            status = "SUCCESS"
            if "Error:" in answer or "System Error" in answer:
                status = "FAILED"
            else:
                success_count += 1
            
            results.append({
                "id": i + 1,
                "question": q,
                "answer": answer,
                "latency": round(latency, 2),
                "status": status
            })
            print(f"      {status} ({round(latency, 2)}s)")
            
            # Small delay between audit questions to respect Vercel limits
            time.sleep(2)
            
        except Exception as e:
            print(f"      CRASHED: {str(e)}")
            results.append({"id": i+1, "question": q, "status": "CRASHED", "error": str(e)})

    # Summary
    avg_latency = sum(r.get("latency", 0) for r in results if "latency" in r) / len(results)
    print(f"\n--- AUDIT COMPLETE ---")
    print(f"Successful Answers: {success_count}/{len(results)}")
    print(f"Average Latency: {round(avg_latency, 2)}s")
    
    with open("audit_report_v2.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_20_questions_test()
