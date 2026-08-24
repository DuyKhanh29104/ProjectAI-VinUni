# [Tên Dự Án]

> **Tài liệu mẫu của repository.** Sao chép file này khi khởi tạo dự án mới; README hiện hành của Label Guardian nằm tại [`README.md`](README.md).

> Tóm tắt 1 câu: [Vấn đề] → [Giải pháp AI] cho [Target User]

## Vấn đề (Problem)

Mô tả pain point cụ thể với data/số liệu:
- Ai đang gặp vấn đề?
- Vấn đề tốn bao nhiêu thời gian/tiền?
- Tại sao các giải pháp hiện tại chưa đủ?

## Giải pháp (Solution)

Sản phẩm giải quyết vấn đề như thế nào bằng AI:
- Feature 1: [mô tả]
- Feature 2: [mô tả]
- Feature 3: [mô tả]

## Target User

- Primary: [mô tả user chính]
- Secondary: [mô tả user phụ]

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI Agent | LangGraph + [LLM] |
| Backend | FastAPI + Python 3.12+ |
| Frontend | React/Next.js + TypeScript |
| Database | PostgreSQL / SQLite |
| DevOps | Docker + GitHub Actions |

## Quick Start

```bash
# 1. Clone repo
git clone https://github.com/a20-ai-thuc-chien/A20-App-XXX.git
cd A20-App-XXX

# 2. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies
python -m pip install --upgrade pip
python -m pip install -e ".[agent,ingestion]" --group dev

# 4. Run development server
uvicorn src.main:app --reload
```

## Project Structure

```
├── src/
│   ├── agents/          # LangGraph agent definitions
│   │   ├── graph.py     # Main graph (nodes + edges)
│   │   ├── state.py     # State schema
│   │   ├── nodes/       # Individual nodes
│   │   └── tools/       # Agent tools
│   ├── api/             # FastAPI routes
│   ├── models/          # Pydantic schemas
│   ├── services/        # Business logic
│   ├── config.py        # Settings
│   └── main.py          # App entry point
├── tests/               # Test suite
├── docs/                # Documentation
├── eval/                # Evaluation results
├── presentation/        # Demo materials
├── Dockerfile           # Multi-stage build
├── docker-compose.yml   # Full stack
└── .github/workflows/   # CI/CD pipelines
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /api/v1/chat | Chat with agent |
| POST | /api/v1/analyze | Analyze input |

## Deliverables Checklist

- [x] Source Code (GitHub)
- [x] README.md
- [x] Architecture Diagram (`docs/architecture_diagram.md`)
- [x] AI Logs (auto-collected)
- [ ] Live URL / Deploy
- [ ] Video Demo
- [ ] Pitch Deck (`presentation/`)
- [x] Weekly Journal (`JOURNAL.md`)
- [x] Worklog (`WORKLOG.md`)
- [ ] Evaluation Evidence (`eval/results/`)

## Team

| Member | Role | Student ID |
|--------|------|-----------|
| [Name] | [Role] | [ID] |
| [Name] | [Role] | [ID] |
| [Name] | [Role] | [ID] |

## License

MIT
