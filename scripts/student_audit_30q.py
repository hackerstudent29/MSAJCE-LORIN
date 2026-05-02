import os
import asyncio
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.append(os.getcwd())
load_dotenv()

from core.engine import RAGEngine

QUESTIONS = [
    "What are the most active technical clubs at MSAJCE right now?",
    "I'm into coding—does the college have a competitive programming or hackathon culture?",
    "Can you tell me more about the RAISE Center and how students can get involved in projects there?",
    "What are the details of the 'Google Cloud' and 'AWS' technology centres on campus?",
    "I heard there's a drone technology lab—where is it and who can access it?",
    "Does the college host a national-level cultural fest or symposium?",
    "What is the 'Zenify' and 'Zenpay' project I keep hearing about in the tech team?",
    "Who are the top student developers I should connect with for help on full-stack projects?",
    "How do I join the IEEE or CSI student chapters?",
    "Are there any internship opportunities within the campus through the Incubation Centre?",
    "Which IT companies allow students to do 'Work From Campus' internships?",
    "What are the rules for using the sports facilities after college hours?",
    "Is the Wi-Fi available 24/7 in the hostel, and what's the speed like?",
    "What's the best spot on campus for a group study session?",
    "Are there any student-run startups currently incubated at MSAJCE?",
    "What are the specific perks for students who participate in the Industry-Backed Technology Centres?",
    "How can I apply for the Pragati scholarship for girls?",
    "What kind of skill development courses are offered for CSE students in the evening?",
    "Does the canteen serve biryani on special days, and how is the food quality?",
    "Is there a gym facility for students staying in the hostel?",
    "What are the library hours for exam periods—does it stay open late?",
    "Can I work on my own projects in the lab after the scheduled classes?",
    "Who is the Physical Education Director I should talk to for joining the cricket team?",
    "Are there any student exchange programs with foreign universities?",
    "How does the college support students who want to clear GATE or UPSC exams?",
    "I want to learn Japanese or German—does the college still offer those language classes?",
    "What was the theme of the last 'Hack MSAJCE' event?",
    "Who are the office bearers for the student council this year?",
    "Is there a specific lab for VLSI and Embedded Systems design?",
    "What are the 'Must-Visit' places or events for a first-year student?"
]

async def run_student_audit():
    print("INITIALIZING STUDENT PERSONA AUDIT (30 QUESTIONS)...")
    try:
        engine = RAGEngine()
    except Exception as e:
        print(f"FAILED TO INITIALIZE ENGINE: {e}")
        return

    results = []

    for i, q in enumerate(QUESTIONS):
        print(f"[{i+1}/30] Student Query: {q}")
        full_response = ""
        
        try:
            # Rate limit buffer (Aggressive for 30-q stability)
            await asyncio.sleep(8)
            
            async for chunk in engine.query_stream(q, history=None):
                if isinstance(chunk, str):
                    full_response += chunk
            
            print(f"DONE. Response length: {len(full_response)}")
            
            # Ground Truth Validation for Students
            fails = []
            # Specific student logic checks
            if "RAISE" in q.upper() and "Innovation" not in full_response and "Startup" not in full_response:
                fails.append("MISSING_RAISE_CONTEXT")
            if "LANGUAGE" in q.upper() and ("Japanese" not in full_response and "German" not in full_response):
                fails.append("MISSING_LANG_TRUTH")
            
            results.append({
                "id": i+1,
                "question": q,
                "response": full_response,
                "passed": len(fails) == 0,
                "fails": fails
            })
            
        except Exception as e:
            print(f"ERROR on Q{i+1}: {str(e)}")
            results.append({
                "id": i+1,
                "question": q,
                "error": str(e),
                "passed": False
            })

    # Save results to a dedicated student audit file
    output_path = r"C:\Users\sthir\.gemini\antigravity\brain\cbc77e23-520c-4673-9e07-ae977d65e97b\scratch\student_audit_30q_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\nSTUDENT AUDIT COMPLETE. Results saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(run_student_audit())
