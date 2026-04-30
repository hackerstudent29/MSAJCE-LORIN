---
title: Lorin - MSAJCE Institutional AI Assistant
emoji: 🤖
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: false
---

# 🤖 Lorin: MSAJCE Institutional AI Assistant

**Lorin** is a high-performance Retrieval-Augmented Generation (RAG) assistant designed specifically for the **Mohamed Sathak A.J. College of Engineering (MSAJCE)**. It serves as a conversational "institutional brain," providing instant, accurate, and grounded information to students and faculty.

---

## 🎯 Purpose
Institutional information (Admission procedures, faculty details, placement records, scholarship eligibility) is often buried in complex PDFs and website pages. **Lorin** solves this by:
*   Providing instant 24/7 answers via Telegram.
*   Ensuring 100% factual accuracy using institutional grounding.
*   Simplifying complex administrative data into friendly, readable lists.

## 👥 Built For
*   **Students:** Quick lookup for scholarships, event details, and transport routes.
*   **Faculty:** Fast access to institutional protocols and committee information.
*   **Aspirants:** Instant answers regarding admission criteria and department highlights.

---

## 🛠️ Technology Stack
The architecture is built for speed, precision, and low latency:

*   **Logic:** Python 3.11 + `python-telegram-bot` (Polling Engine)
*   **Intelligence:** GPT-4o-mini (LLM) & Cohere V3 (Reranking)
*   **Knowledge Base:** Pinecone (Vector Store) & BM25s (Lexical Search)
*   **Memory:** Upstash Redis (Contextual Conversation History)
*   **Observability:** Langfuse & LangSmith (Telemetry & Evaluation)
*   **Deployment:** Hugging Face Spaces (Docker-based 24/7 Service)

---

## ✨ Key Features
*   **Grounding (No Hallucinations):** Lorin only answers using the provided institutional documents.
*   **Multi-Turn Intelligence:** Remembers previous questions (e.g., "Tell me more about him").
*   **Interactive Design:** Mandates interactive closing questions to keep users engaged.
*   **Optimized Retrieval:** Uses a Hybrid Search strategy (Vector + Keyword) for 99% accuracy on names and codes.

---

## 🏗️ Architecture
For a detailed look at the internal RAG pipeline, please refer to:
*   [Documentation Overview](docs/PIPELINE.md)
*   [Architecture Diagram](docs/PIPELINE.mermaid)

---

## ⚠️ Disclaimer
This assistant is an AI-powered tool using publicly available institutional data. It is intended for informational purposes and should be verified with official college documentation for high-stakes administrative decisions.

---
*Developed with ❤️ for the MSAJCE Community.*
