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

## Container deployment

The root Compose file now runs MySQL, Qdrant, the Django API, and the separate
RAG worker. It is designed to sit behind an HTTPS reverse proxy: the database
and API ports bind only to `127.0.0.1` by default.

Before starting it, create a private root `.env` from `.env.example` and set
at least `DB_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `OLLAMA_API_KEY`, and `OLLAMA_MODEL`. For a public
domain, set `DJANGO_DEBUG=False`, `DJANGO_CSRF_TRUSTED_ORIGINS` to its HTTPS
origin, `DJANGO_BEHIND_HTTPS_PROXY=True`, and `DJANGO_SECURE_SSL_REDIRECT=True`
only after the reverse proxy is serving TLS. Once HTTPS is confirmed, set
`DJANGO_HSTS_SECONDS=31536000`; enable the HSTS subdomain and preload options
only when every relevant subdomain supports HTTPS.

```bash
docker compose up --build -d
```

The API health check is available at `http://127.0.0.1:8000/api/v1/health/`.
Index factsheets after Qdrant starts; indexing is intentionally not performed
by web requests or container startup.
