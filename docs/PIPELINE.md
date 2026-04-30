# 🧠 Lorin RAG Intelligence Suite: Architecture Pipeline

This document outlines the **Tier 2 Institution-Grade** RAG pipeline used by the MSAJCE Campus Buddy.

## 🏗️ The Decision Intelligence Flow

```mermaid
graph TD
    %% Input Stage
    U[User Query] --> PP[Pre-Flight Processor]
    
    subgraph "1. Query Understanding Layer"
        PP -->|Detect Intent| C[Factual vs Other]
        PP -->|Preserve Constraints| R[Query Rewriting]
        PP -->|Complexity Check| CMP[Simple vs Complex]
    end

    %% Retrieval Stage
    R --> HR[Hybrid Retrieval Engine]
    
    subgraph "2. Hybrid Memory Layer"
        HR --> VEC[Vector Search: Pinecone]
        HR --> LEX[Lexical Search: BM25s]
        VEC & LEX --> FUSE[Reciprocal Rank Fusion]
        FUSE --> RNK[Cohere Rerank v3.0]
    end

    %% Reasoning Stage
    RNK --> AG[Answerability Gate]
    RNK --> CD[Conflict Detection Layer]

    subgraph "3. Reasoning & Decision Layer"
        AG -->|Insufficient| REF[Polite Refusal]
        AG -->|Sufficient| GEN[Lorin Generator]
        CD -->|Conflict Found| GEN
    end

    %% Verification Stage
    GEN --> DHC{Deterministic Hard-Check}
    
    subgraph "4. Multi-Stage Verification"
        DHC -->|Regex Failure| REJ[Audit Rejection]
        DHC -->|Regex Pass| ADP{Adaptive Shortcut}
        ADP -->|Simple Query| OUT[Final Response]
        ADP -->|Complex Query| SLA[Secondary LLM Audit]
        SLA -->|Verified| OUT
        SLA -->|Hallucination| REJ
    end

    %% Telemetry
    OUT --> LS[(LangSmith Tracing)]
    OUT --> RD[(Upstash Redis Logs)]
```

## 🛡️ Hardening Features

| Feature | Implementation | Purpose |
| :--- | :--- | :--- |
| **Deterministic Gate** | Regex-based value matching | Ensures numbers/times in the answer exist in the source text. |
| **Conflict Detector** | LLM Cross-referencing | Identifies if different sources provide contradictory information. |
| **Adaptive Pipeline** | Complexity short-circuiting | Reduces latency for simple lookups by skipping the secondary audit. |
| **Constraint Locking** | Pre-processor rewriting | Prevents the loss of critical modifiers (e.g., "morning", "temporary"). |
| **Source Attribution** | Forced `[Source X]` tags | Mandates that every factual claim is traceable to a specific chunk. |

## 🛠️ Tech Stack Highlights
- **Reasoning**: GPT-4o Mini
- **Embeddings**: text-embedding-3-small
- **Reranking**: Cohere English v3.0
- **Vector DB**: Pinecone Serverless
- **Lexical DB**: Local BM25s
- **Telemetry**: LangSmith
- **Cache**: Upstash Redis
