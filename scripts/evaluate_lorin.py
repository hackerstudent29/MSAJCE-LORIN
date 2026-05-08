import asyncio
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine import RAGEngine

# THE GOLDEN EVALUATION SET
EVAL_CASES = [
    {
        "id": "CSI_VP",
        "query": "Who is the Vice President of CSI?",
        "expected_keywords": ["Saqlin", "Mustaq"],
        "category": "Identity"
    },
    {
        "id": "WESLIN_ROLE",
        "query": "Who is Weslin D?",
        "expected_keywords": ["Associate Professor", "Information Technology", "IT"],
        "category": "Faculty"
    },
    {
        "id": "COLLEGE_CODE",
        "query": "What is the college code for MSAJCE?",
        "expected_keywords": ["1301"],
        "category": "Identity"
    },
    {
        "id": "BUS_COUNT",
        "query": "How many buses does the college have?",
        "expected_keywords": ["22"],
        "category": "Infrastructure"
    },
    {
        "id": "IIC_PRESIDENT",
        "query": "Who is the IIC President?",
        "expected_keywords": ["Janarthanan"],
        "category": "Identity"
    }
]

async def run_eval():
    load_dotenv()
    engine = RAGEngine()
    results = []
    
    print(f"\n[START] LORIN PRODUCTION EVALUATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    passed = 0
    for case in EVAL_CASES:
        print(f"Testing {case['id']}: '{case['query']}'...")
        
        response_text = ""
        async for chunk in engine.query_stream(case["query"]):
            if isinstance(chunk, str):
                response_text += chunk
        
        # Check for keywords (Simple heuristic for now)
        success = all(kw.lower() in response_text.lower() for kw in case["expected_keywords"])
        
        if success:
            print(f"  PASS")
            passed += 1
        else:
            print(f"  FAIL")
            print(f"     Expected: {case['expected_keywords']}")
            print(f"     Got: {response_text[:100]}...")
            
        results.append({
            **case,
            "actual_response": response_text,
            "status": "PASS" if success else "FAIL"
        })
        
    print("="*60)
    print(f"SUMMARY: {passed}/{len(EVAL_CASES)} Cases Passed ({(passed/len(EVAL_CASES))*100:.1f}%)")
    
    # Save report
    report_path = os.path.join(os.getcwd(), "data", "eval_reports")
    os.makedirs(report_path, exist_ok=True)
    report_file = os.path.join(report_path, f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Report saved to: {report_file}\n")

if __name__ == "__main__":
    asyncio.run(run_eval())
