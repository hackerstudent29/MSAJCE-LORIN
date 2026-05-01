import csv
import os
import random
from datetime import datetime, timedelta

def generate_mock_forensic_csv():
    data_path = os.path.join("data", "sunday_forensic_report.csv")
    os.makedirs("data", exist_ok=True)
    
    headers = ["timestamp", "session_id", "query", "category", "score", "hits_pinecone", "hits_bm25", "latency_ms", "status"]
    
    queries = [
        ("Who is Dr. Weslin D?", "INSTITUTIONAL"),
        ("Tell me about the Principal", "INSTITUTIONAL"),
        ("IT department research areas", "INSTITUTIONAL"),
        ("Bus timings for route 15", "INSTITUTIONAL"),
        ("Who developed Lorin?", "DEVELOPER"),
        ("Hello", "GREETING"),
        ("How to apply for admission?", "INSTITUTIONAL"),
        ("Dr. Kannan S patents", "INSTITUTIONAL")
    ]
    
    rows = []
    base_time = datetime.now() - timedelta(days=1)
    
    for i in range(25):
        q, cat = random.choice(queries)
        row = {
            "timestamp": (base_time + timedelta(minutes=i*15)).isoformat(),
            "session_id": f"sess_{1000 + i}",
            "query": q,
            "category": cat,
            "score": round(random.uniform(0.75, 0.98), 4),
            "hits_pinecone": random.randint(3, 10),
            "hits_bm25": random.randint(2, 8),
            "latency_ms": random.randint(1200, 4500),
            "status": "SUCCESS"
        }
        rows.append(row)
        
    with open(data_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"DONE: Mock forensic report generated at {data_path}")
    return data_path

if __name__ == "__main__":
    generate_mock_forensic_csv()
