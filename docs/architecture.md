# System Architecture

This document is the submission-ready architecture diagram for the **Mutual Fund Portfolio Intelligence Agent**. It describes the deployed Django/React product, the tool-using portfolio agent, and the evidence-backed document-research path.

## Logical architecture

```mermaid
flowchart TB
    classDef client fill:#E8F3ED,stroke:#226B47,color:#153A28,stroke-width:2px
    classDef api fill:#EAF2FF,stroke:#2563EB,color:#16325C,stroke-width:2px
    classDef intelligence fill:#FFF3D9,stroke:#D97706,color:#713F12,stroke-width:2px
    classDef data fill:#FCE7F3,stroke:#BE185D,color:#701A3A,stroke-width:2px
    classDef external fill:#F3F4F6,stroke:#4B5563,color:#1F2937,stroke-width:2px
    classDef worker fill:#F3E8FF,stroke:#7E22CE,color:#4C1D95,stroke-width:2px

    USER([Investor]):::client --> WEB[React + Vite web application]:::client

    WEB -->|Session cookie + CSRF| AUTH[Authentication API<br/>signup · login · profile]:::api
    WEB -->|Portfolio requests| PORTFOLIO[Portfolio / Explorer APIs]:::api
    WEB -->|Portfolio Chat| CHAT[Chat API]:::api
    WEB -->|Fund document question| RAG_API[RAG API<br/>direct answer or queued job]:::api

    AUTH --> MYSQL[(MySQL<br/>users · portfolios · chats · RAG jobs)]:::data
    PORTFOLIO --> MYSQL

    CHAT --> ORCH[Single-agent orchestrator]:::intelligence
    ORCH --> REGISTRY[Validated tool registry<br/>Pydantic contracts + user binding]:::intelligence
    REGISTRY --> PORT_TOOLS[Portfolio analysis tools<br/>holdings · overlap · exposure · calculators]:::intelligence
    PORT_TOOLS --> MYSQL
    REGISTRY --> NAV[MFapi.in NAV tools]:::external
    REGISTRY --> RETRIEVAL[Fund-scoped retrieval bridge<br/>retrieval only — no second answer model]:::intelligence
    RETRIEVAL --> QDRANT[(Qdrant<br/>vectors + page metadata)]:::data
    ORCH <-->|tool-calling / answer| OLLAMA[Ollama Cloud model]:::external

    RAG_API -->|create job| JOBS[RAG job records]:::data
    JOBS --> WORKER[Dedicated RAG worker]:::worker
    WORKER --> RAG_SERVICE[RAG service<br/>retrieval · grounding · citations]:::intelligence
    RAG_API --> RAG_SERVICE
    RAG_SERVICE --> QDRANT
    RAG_SERVICE <-->|answer / optional vision fallback| OLLAMA

    PDF[Fund factsheet PDFs]:::external --> DOCLING[Docling ingestion<br/>GPU when available]:::intelligence
    DOCLING --> MARKDOWN[Table-aware Markdown<br/>+ semantic chunks]:::data
    MARKDOWN --> QDRANT

    CHAT --> RESPONSE[Grounded answer<br/>sources · chunks · method · confidence]:::client
    RAG_API --> RESPONSE
    RESPONSE --> WEB
```

### Key data flows

| Flow | What happens | Safety / quality control |
| --- | --- | --- |
| Portfolio Chat | The agent selects from registered tools, then combines portfolio calculations, NAV data, or factsheet evidence into an answer. | Tool inputs are validated; the authenticated user identity is injected server-side rather than accepted from the model. |
| Fund document research | The API returns an answer directly or stores a RAG job; the worker processes longer jobs without holding the browser request open. | Fund scope, page metadata, citations, grounding checks, confidence, and retrieved chunks are preserved. |
| Document ingestion | A PDF is processed into table-aware Markdown and chunks before embeddings are stored in Qdrant. | Ingestion is separate from question answering, so user requests do not block on PDF parsing. |
| Fund Explorer | Public NAV data is retrieved from MFapi.in to compare funds independently of a user’s portfolio. | Exact scheme selection and source/date metadata help avoid ambiguous fund-plan answers. |

The agent’s `search_financial_documents` tool is deliberately **retrieval-only**.
It returns page-addressable chunks to the same agent turn; it does not invoke a
second answer-generating RAG model. The agent is the component that combines
those chunks with portfolio or NAV results.

---

## Container deployment architecture

```mermaid
flowchart LR
    classDef service fill:#EAF2FF,stroke:#2563EB,color:#16325C,stroke-width:2px
    classDef storage fill:#FCE7F3,stroke:#BE185D,color:#701A3A,stroke-width:2px
    classDef boundary fill:#E8F3ED,stroke:#226B47,color:#153A28,stroke-width:2px

    BROWSER[Browser / React dev server]:::boundary -->|HTTP API calls| API

    subgraph COMPOSE[Docker Compose]
        API[Django API + Gunicorn]:::service
        WORKER[Dedicated RAG worker]:::service
        DB[(MySQL volume)]:::storage
        VECTOR[(Qdrant volume)]:::storage

        API --> DB
        API --> VECTOR
        WORKER --> DB
        WORKER --> VECTOR
    end

    API -->|HTTPS provider API| OLLAMA[Ollama Cloud]:::boundary
    API -->|Public NAV data| MFAPI[MFapi.in]:::boundary
```

### Runtime responsibilities

| Service | Responsibility | Readiness behavior |
| --- | --- | --- |
| `db` | MySQL data for accounts, portfolios, chats, and RAG job state. | Docker health check waits for the database account to respond. |
| `qdrant` | Persistent semantic index for factsheet chunks and metadata. | Stores 768-dimensional vectors plus text, PDF, page, fund, and publication metadata in a separate persistent service. |
| `api` | Django REST API, authentication, portfolio features, agent chat, direct RAG endpoint, and health endpoint. | Runs migrations/static collection, then Gunicorn; `/api/v1/health/` checks database readiness. |
| `rag_worker` | Claims queued RAG jobs and persists completed answers, evidence, citations, and usage. | Starts only after the API health check passes. |

> [!NOTE]
> In the provided Compose configuration, MySQL, Qdrant, and the API bind to `127.0.0.1` by default. A public deployment should place an HTTPS reverse proxy in front of the API and configure allowed hosts, CSRF origins, secure redirect, and HSTS through environment variables.

---

## Evidence path for a fund question

```mermaid
sequenceDiagram
    autonumber
    participant U as Investor
    participant W as React UI
    participant A as Django API
    participant G as Agent / RAG service
    participant Q as Qdrant
    participant L as Ollama Cloud

    U->>W: Ask a fund or portfolio question
    W->>A: Authenticated API request
    A->>G: Validated request + trusted user identity
    G->>Q: Resolve one fund scope and retrieve relevant chunks
    Q-->>G: Text, document, page, score, metadata
    G->>L: Answer using retrieved evidence and tool results
    L-->>G: Draft answer / tool calls
    G-->>A: Grounded answer, citations, confidence, method
    A-->>W: Structured response or persisted RAG-job result
    W-->>U: Answer with evidence panel
```

## Design principles

- **Evidence before assertion:** document answers carry source and page metadata.
- **Scoped retrieval:** fund questions resolve one indexed fund before querying the collection.
- **Separation of concerns:** ingestion, interactive API requests, and background RAG work are separate processes.
- **Least privilege:** browser identity is authenticated by Django; internal tool identity is bound server-side.
- **Operational resilience:** containers have health checks, persistent data volumes, environment-based configuration, and no committed secrets.

## API paths represented in this diagram

| Path | Role |
| --- | --- |
| `POST /api/v1/chat/` | Authenticated portfolio-agent conversation. |
| `POST /api/v1/rag/jobs/` | Queues a document-research request for the worker. |
| `GET /api/v1/rag/jobs/{job_id}/` | Returns RAG job status and the completed evidence-backed result. |
| `POST /api/v1/rag/answer/` | Direct/synchronous document-research answer. |
| `/api/v1/auth/` | Signup, login, logout, profile, and CSRF endpoints. |
| `/api/v1/health/` | Database-aware API readiness endpoint. |
