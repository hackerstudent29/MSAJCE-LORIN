import asyncio
import os
import sys
import time
import json
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

QUESTIONS = [
    # ALUMNI & SUCCESS (1-10)
    "Do we have any alumni currently working at Microsoft or Google?",
    "Which MSAJCE graduate holds the record for the highest international placement?",
    "Are there any alumni mentors who visit the campus for tech talks?",
    "Can you name a successful startup founded by an MSAJCE alumnus?",
    "Which batch has the highest number of entrepreneurs?",
    "Does the college maintain an active alumni portal for networking?",
    "Are there any alumni in the civil services (IAS/IPS)?",
    "Which core engineering companies frequently hire our mechanical alumni?",
    "Do alumni provide internships to current juniors through their companies?",
    "When is the next grand alumni meet scheduled?",

    # RESEARCH & FACULTY (11-20)
    "Which faculty member has the highest number of patents in the EEE department?",
    "What are the major research areas currently active in the IT department?",
    "Does the college provide funding for student-led research projects?",
    "How many IEEE journal papers were published by MSAJCE last year?",
    "Who is the coordinator for the R&D cell?",
    "Can students co-author research papers with professors?",
    "What kind of research is happening in the UAV/Drone technology centre?",
    "Is there a dedicated fund for attending international conferences?",
    "Which department has the most industry-sponsored projects?",
    "Can I use the research labs during the summer break?",

    # PLACEMENT TRAINING (21-30)
    "What are the three phases of the placement training program?",
    "Do we get specific training for Product-Based company interviews?",
    "Who conducts the 'Soft Skills' training sessions for 3rd years?",
    "Is there a mock interview session with industry experts?",
    "When does the 'Aptitude' training phase begin for CSE students?",
    "Do you provide training for the 'AMCAT' or 'CoCubes' assessments?",
    "What is the average placement rate for the AIDS department?",
    "Which companies come specifically for 'On-Campus' drive in September?",
    "Does the college provide 'Japanese' language training for Japanese placements?",
    "Is there a dedicated 'Placement Cell' office I can visit?",

    # INFRASTRUCTURE & LIBRARY (31-40)
    "Does the library provide access to IEEE Xplore digital library?",
    "How many NPTEL local chapter videos are available in the library?",
    "Can I borrow more than 3 books if I am a top ranker?",
    "Is there a separate reading room for competitive exam preparation?",
    "What are the specifications of the systems in the High-Performance Computing lab?",
    "Does the college have a 3D printing facility for student projects?",
    "Is the entire campus covered by high-speed Wi-Fi?",
    "What are the working hours of the Digital Library?",
    "Are there any smart classrooms in the Mechanical department?",
    "Does the college have an indoor auditorium for tech fests?",

    # HOSTEL & SPORTS (41-50)
    "What is the daily mess menu for the Girls Hostel?",
    "Does the hostel have a dedicated laundry service or washing machines?",
    "What gym equipment is available in the boys' hostel gym?",
    "Can I play football or cricket on the grounds after 6 PM?",
    "Is there a doctor on call for hostel emergencies at night?",
    "What are the timings for the hostel mess on Sundays?",
    "Do we have a dedicated basketball court with floodlights?",
    "Are there any indoor games like Table Tennis available in the common room?",
    "What is the procedure for a hosteller to use the lab after 9 PM?",
    "Is there a shop inside the campus for basic stationery and snacks?"
]

async def run_audit():
    print(f"INITIALIZING FORENSIC AUDIT BATCH 3 ({len(QUESTIONS)} QUESTIONS)...")
    engine = RAGEngine()
    results = []
    
    for i, q in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] Student Query: {q}")
        full_response = ""
        
        try:
            # Rate limit buffer
            await asyncio.sleep(8)
            
            async for chunk in engine.query_stream(q, history=None):
                if isinstance(chunk, str):
                    full_response += chunk
            
            # Simple validation: If response is too short or contains "don't know", flag it
            status = "PASS"
            if "don't have" in full_response.lower() or "not mention" in full_response.lower() or len(full_response) < 50:
                status = "FAIL/WEAK"
            
            results.append({
                "id": i,
                "query": q,
                "response": full_response,
                "status": status
            })
            print(f"DONE. Status: {status}\n")
            
        except Exception as e:
            print(f"ERROR on Q{i}: {e}")
            results.append({"id": i, "query": q, "error": str(e), "status": "ERROR"})

    # Save Audit Results
    with open("data/audits/audit_results_batch_3.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"AUDIT BATCH 3 COMPLETE. Results saved to 'data/audits/audit_results_batch_3.json'")

if __name__ == "__main__":
    asyncio.run(run_audit())
