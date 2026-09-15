# Architecture Diagram

> Sơ đồ tóm tắt kiến trúc đang triển khai. Xem [`ARCHITECTURE.md`](../ARCHITECTURE.md) để biết contract, luồng dữ liệu và các quyết định kiến trúc đầy đủ.

## Production topology

```mermaid
flowchart LR
    User[Reviewer / Admin] -->|HTTPS| FE[React + Vite SPA<br/>Vercel]
    FE -->|Supabase session| Auth[Supabase Auth]
    FE -->|REST API /api/v1| API[FastAPI backend<br/>VM + Docker Compose]
    API -->|Verify identity| Auth
    API --> DB[(PostgreSQL<br/>Supabase)]
    API --> GCS[(Private GCS<br/>images and labels)]
    API --> QA[Deterministic QA pipeline<br/>optional LLM advisory]
    QA --> DB
    Batch[GCP Batch ingestion] --> GCS
    Batch --> DB
```

## Review and revision flow

```mermaid
sequenceDiagram
    participant R as Reviewer
    participant F as Frontend
    participant A as FastAPI
    participant D as PostgreSQL
    participant G as GCS

    R->>F: Open QA case or 2D Editor
    F->>A: Request case/frame with session token
    A->>D: Load metadata, issues and latest revision
    A->>G: Sign or stream private assets
    A-->>F: Case data and asset URLs
    R->>F: Edit annotation and submit decision
    F->>A: Save revision with expected version
    A->>D: Append immutable revision and audit event
    A-->>F: Updated case state
```

## Responsibility boundaries

| Component | Responsibility |
| --- | --- |
| React/Vite frontend | Authentication UX, QA queue/case views, reports, settings and 2D editing |
| FastAPI backend | Authorization, API contracts, QA orchestration, revision/audit rules and asset access |
| PostgreSQL/Supabase | Application state, roles, cases, issues, revisions and audit data |
| Private GCS | Dataset images, labels and other large immutable assets |
| GCP Batch | Long-running official dataset ingestion outside request/response traffic |
