import asyncio
import os
import sys

# Disable langsmith for testing
os.environ["LANGSMITH_TRACING"] = "false"

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

async def main():
    engine = RAGEngine()
    
    questions = [
        "My son wants a top-tier college; what does the NAAC A+ Grade actually mean for his degree?",
        "Is the NBA Accreditation valid for all departments, or just a few?",
        "How does MSAJCE rank compared to other colleges on the OMR IT corridor?",
        "What was the highest salary package offered to a student in the 2024 batch?",
        "Does the college provide internships at Siruseri IT Park since it's right next door?",
        "If my daughter studies Cyber Security, which companies will recruit her?",
        "Do you provide training for TCS, Infosys, and Cognizant interview?",
        "What happens if my child doesn't get placed in the first round of campus interviews?",
        "Are there any scholarships available for students with high marks?",
        "Can we pay the semester fees online through the college portal?",
        "What is the Management Quota seat count for the AI & Machine Learning department?",
        "Is there a lateral entry option for diploma students into the third year?",
        "How is the hostel security for girls, and what are the outing rules?",
        "Does the college provide bus transport to areas like Tambaram or North Chennai?",
        "What kind of food is served in the mess, and is it hygienic?",
        "What are the lab facilities like for the new AIDS and CSBS departments?",
        "Is the campus strictly Anti-Ragging, and who is the person in charge of safety?",
        "Does the college support students who want to study or intern abroad?",
        "If my child is struggling with a subject, do you have extra coaching or remedial classes?",
        "What are the working hours of the library for students staying in the hostel?"
    ]
    
    with open(r"d:\.gemini\claude RAG\data\audits\test_20_results.txt", "w", encoding="utf-8") as f:
        for i, q in enumerate(questions, 1):
            f.write(f"\n==============================================\n")
            f.write(f"Q{i}: {q}\n")
            f.write(f"----------------------------------------------\n")
            f.flush()
            try:
                full_ans = ""
                async for chunk in engine.query_stream(q):
                    if isinstance(chunk, str):
                        full_ans += chunk
                f.write(f"A: {full_ans.strip()}\n")
                f.flush()
                print(f"Completed Q{i}")
            except Exception as e:
                f.write(f"Error querying: {e}\n")
                f.flush()
                print(f"Error on Q{i}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
