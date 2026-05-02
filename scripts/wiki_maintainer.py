import json
import os
import re

WIKI_DIR = "data/wiki"
JSON_DIR = "data/jsons"

class WikiMaintainer:
    def __init__(self):
        os.makedirs(WIKI_DIR, exist_ok=True)
        self.master_data = self._load_master()

    def _load_master(self):
        master_path = "data/unified_master_chunks.json"
        if os.path.exists(master_path):
            with open(master_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def synthesize_overview(self):
        """Builds a high-level college overview Wiki page."""
        filename = "COLLEGE_OVERVIEW.md"
        # Find relevant chunks
        about_chunks = [c for c in self.master_data if "about" in c["metadata"].get("source_file", "").lower()]
        stats_chunks = [c for c in self.master_data if "stats" in c["metadata"].get("section", "").lower()]
        
        content = [
            "# 🏛️ MSAJCE — Institutional Overview (Master Wiki)",
            "**Source:** Compiled from MSAJCE Knowledge Base",
            "",
            "## 📍 Location & Identity",
            "- **Name:** Mohamed Sathak A.J. College of Engineering (MSAJCE)",
            "- **Location:** SIPCOT IT Park, OMR, Chennai",
            "- **Counselling Code:** 1301",
            "- **Accreditation:** NAAC A+ Grade, NBA Accredited Programs",
            "",
            "## 🎓 Academic Excellence",
            "MSAJCE is a premier technical institution offering specialized engineering programs. It is known for its proximity to top MNCs and its focus on industry-ready skills.",
            ""
        ]
        
        # Add highlights from about chunks
        for c in about_chunks[:3]:
            text = c["text"].split('\n')[0] # First line/sentence
            content.append(f"• {text}")

        with open(os.path.join(WIKI_DIR, filename), 'w', encoding='utf-8') as f:
            f.write("\n".join(content))
        print(f"DONE: Generated {filename}")

    def synthesize_admissions(self):
        """Builds a step-by-step Admission Master Wiki."""
        filename = "ADMISSION_MASTER.md"
        content = [
            "# ADMISSION MASTER GUIDE",
            "**Status:** Production Ground Truth",
            "",
            "## PROCESS ROADMAP",
            "1. **Registration:** Apply online at [MSAJCE Enrollment](https://enrollonline.co.in/Registration/Apply/MSAJCE)",
            "2. **Counselling:** Participate in TNEA Counselling using Code **1301**.",
            "3. **Verification:** Submit documents (10th, 12th, Transfer Certificate).",
            "4. **Confirmation:** Pay fees via [FeePayr](https://www.feepayr.com/)",
            "",
            "## CRITICAL CONTACTS",
            "- Admission Head: Dr. K.P. Santhosh Nathan (9840886992)",
            "- General Office: +91 99400 04500",
            ""
        ]
        with open(os.path.join(WIKI_DIR, filename), 'w', encoding='utf-8') as f:
            f.write("\n".join(content))
        print(f"DONE: Generated {filename}")

if __name__ == "__main__":
    maintainer = WikiMaintainer()
    maintainer.synthesize_overview()
    maintainer.synthesize_admissions()
