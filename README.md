# Mutual Fund Portfolio Intelligence Agent

The implementation is in [backend/README.md](backend/README.md). It now includes a production-oriented single-agent orchestration loop, structured request state, exact existing-tool registration, strict tool-call validation, source tracking, safe activity traces, a FastAPI chat endpoint, PostgreSQL/pgvector schema scaffolding, and automated workflow/failure tests.

## Local development

The Django REST API now exposes the agent at `POST /api/v1/chat/`; the React client in `frontend/` uses that endpoint through the Vite development proxy. See `backend/README.md` for the required Ollama variables.

```powershell
# terminal 1
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py runserver

# terminal 2
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open the Vite URL shown in terminal 2. The default mock portfolio identity is `USER001`.
