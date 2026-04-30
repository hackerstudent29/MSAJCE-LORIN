import json
import os

def create_mock_json():
    text_path = r"D:\.gemini\RAG 2\data\03_master\admission.master.txt"
    with open(text_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into sections based on what I saw in the file
    sections = [
        {
            "section": "Programmes Offered & Seats Available",
            "chunk_id": "ADM_001",
            "token_count": 450,
            "text": """NAME OF THE Programme | Total Sanctioned Intake | Government Quota | Management Quota
Civil Engineering | 30 | 15 | 15
Computer Science & Engineering (Permanent Affiliation) | 60 | 30 | 30
Electronics & Communication Engineering | 60 | 30 | 30
Electrical & Electronics Engineering | 30 | 15 | 15
Mechanical Engineering (Permanent Affiliation) | 30 | 15 | 15
Information Technology | 60 | 30 | 30
Artificial Intelligence & Data Science | 30 | 15 | 15
Computer Science & Business Systems | 30 | 15 | 15
Computer Science & Engineering (Cyber Security) | 30 | 15 | 15
Artificial Intelligence & Machine Learning | 60 | 30 | 30
Electronics Engg w/s in VLSI Design & Technology | 30 | 15 | 15
ECE w/s in Advanced Communication Technology | 30 | 15 | 15""",
            "entities": []
        },
        {
            "section": "Admission Eligibility & Criteria",
            "chunk_id": "ADM_002",
            "token_count": 380,
            "text": """B.E. / B.Tech. Degree Programmes (4 Years)
HSC (Academic) or its equivalent with a minimum average percentage:
- General Category: 45.00%
- BC / BCM: 40.00%
- MBC & DNC: 40.00%
- SC / SCA / ST: 40.00%

Direct Second Year (Lateral Entry):
- General Category: 55.00%
- BC / BCM: 50.00%
- MBC & DNC: 45.00%
- SC / SCA / ST: Mere pass""",
            "entities": []
        },
        {
            "section": "Admission Contacts",
            "chunk_id": "ADM_003",
            "token_count": 220,
            "text": "For admission assistance and inquiries, contact the following institutional authorities:",
            "entities": [
                {"name": "Dr.K.S.Srinivasan", "role": "Principal", "department": "MSAJCE"},
                {"name": "Mr.A.Abdul Gafoor", "role": "Administrative Officer", "department": "MSAJCE"},
                {"name": "Dr.K.P.Santhosh Nathan", "role": "Head-Admission", "department": "MSAJCE"},
                {"name": "Mr.S.Syed Abuthahir", "role": "Assistant Professor", "department": "MECH"}
            ],
            "possible_questions": [
                "Who is the head of admissions at MSAJCE?",
                "How to contact the principal for admission queries?"
            ]
        },
        {
            "section": "Scholarships & Financial Aid",
            "chunk_id": "ADM_004",
            "token_count": 310,
            "text": """Pragati scholarship scheme for Girl Students: Max two girl child only per family - Income < 8 Lakh.
Saksham scholarship scheme for specially abled: Disability > 40% - Income < 8 Lakh.
Merit cum based Scholarship: 50% marks - Income < 2.5 Lakh.
Central Sector Scheme: 80% marks - Income < 8 Lakh.""",
            "entities": []
        }
    ]

    data = {
        "metadata": {
            "source_url": "https://www.msajce-edu.in/admission.php",
            "embedding_model": "text-embedding-3-small",
            "scraped_date": "2026-04-27",
            "page_title": "MSAJCE Admission Intelligence Extraction"
        },
        "chunks": sections
    }

    with open("msajce_admission.json", "w", encoding='utf-8') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    create_mock_json()
