# Mutual Fund Portfolio Intelligence — Single Agent

This backend uses **one Ollama Cloud agent with many registered tools**. The orchestration layer reuses the existing portfolio, research, analysis, and NAV tools; it does not duplicate their formulas or data access.

## Architecture

```text
POST /api/chat
      |
      v
SingleAgentOrchestrator
  |-- intent guardrail selects only relevant registered tools
  |-- an Ollama Cloud model chooses the next tool from that set
  |-- registry validates arguments and binds authenticated user_id
  |-- existing tool returns structured data/error/provenance
  |-- request state retains results, sources, and safe activity trace
  `-- loop ends with an evidence-based answer (max 12 iterations/20 calls)
```

Important files:

- `app/agent/orchestrator.py` — bounded sequential tool loop, retry limits, safe trace, and response contract.
- `app/agent/ollama.py` — Ollama Cloud native chat/function-calling adapter. The loop itself is provider-neutral and testable without a live model.
- `app/agent/state.py` — per-request structured state for portfolio, fund, company, RAG, web, analysis, sources, and errors.
- `app/agent/policy.py` — narrow intent guardrail. It does not calculate or answer; it prevents irrelevant calls such as web search for a portfolio-total question.
- `app/agent/tool_registry.py` — exact existing function registration, JSON schemas, strict validation, identity binding, and execution.
- `app/tools/core.py` and `app/tools/nav.py` — existing deterministic/retrieval tools.
- `app/api/main.py` — FastAPI endpoints, including `/api/chat` and the backward-compatible `/agent/query`.

The model never receives a `user_id` tool argument. The API-supplied identity is injected by the executor, so a model-generated call cannot read another user's portfolio. Tool results remain structured between calls. The client receives high-level activities, never chain-of-thought or raw internal state.

## Registered tools

- Portfolio: `get_portfolio`, `get_fund_holdings`, `calculate_exposure`, `calculate_fund_overlap`, `calculate_sector_exposure`, `calculate_portfolio_risk`
- Knowledge/RAG: `search_financial_documents`, `get_mutual_fund_details`, `get_historical_performance`
- Current research: `web_search`, `search_company_news`, `get_market_data`, `research_company`
- Analysis: `simulate_allocation`, `compare_scenarios`, `calculate_tax_impact`, `analyze_goal`, `validate_analysis`
- MFapi.in/NAV: `search_mutual_fund_schemes`, `get_mutual_fund_nav`, `calculate_lump_sum_value`, `get_nav_history`, `calculate_cagr`, `calculate_volatility`, `calculate_drawdown`, `compare_funds`

Current adapter status matters: portfolio/fund calculations use timestamped mock JSON; NAV tools use public MFapi.in data; fund-document search uses persistent Qdrant and indexed factsheets; the general web-search provider remains unconfigured. The agent is instructed to surface those limitations and never substitute invented evidence.

### MFapi.in data in Portfolio Chat

The same Django/React Portfolio Chat can now look up a named scheme's latest or historical NAV and calculate a one-time investment's NAV-based value. It resolves exact MFapi.in scheme names and refuses to choose an arbitrary Direct/Regular or Growth/IDCW variant. NAV and scheme-search responses are cached briefly to limit provider calls; responses include the provider URL and data-as-of date. The lump-sum estimate uses the earliest available NAV when no start date is supplied (which may not equal the scheme's legal inception), and is explicitly not an SIP or benchmark calculation.

Example chat questions:

- “What is the latest NAV for HDFC ELSS Tax Saver Fund - Regular Plan - Growth?”
- “What was the NAV for HDFC ELSS Tax Saver Fund - Regular Plan - Growth on 2026-08-31?”
- “What would ₹10,000 invested in HDFC ELSS Tax Saver Fund - Regular Plan - Growth be worth now?”

If MFapi.in returns multiple plan variants, specify the exact plan and option. Continue to use factsheet retrieval for official benchmark, published performance, and SIP table figures. Chat's answer-method status reports whether MFapi.in, RAG, both, or neither supplied data.

The Fund Explorer uses the same public provider independently of a user's imported portfolio. It exposes:

- `GET /api/v1/funds/search/?q=HDFC%20ELSS&limit=12` — search exact scheme names and codes.
- `GET /api/v1/funds/nav-overview/{scheme_code}/` — latest available NAV and 1/3/5-year trailing NAV CAGR where sufficient history exists.
- `POST /api/v1/funds/nav-compare/` — compare 2–5 selected scheme codes using NAV CAGR, annualized volatility, and maximum drawdown for 1, 3, 5, or 10 years.

The comparison is NAV-history based, not benchmark adjusted; the Explorer does not imply ratings, assets under management, or recommendations that this provider does not supply.

Example chains:

```text
How much have I invested?
  get_portfolio

Which companies am I indirectly invested in?
  get_portfolio -> get_fund_holdings -> calculate_exposure

Do my mutual funds overlap?
  get_portfolio -> get_fund_holdings -> calculate_fund_overlap

I have ₹30,000 more; compare scenarios.
  get_portfolio -> relevant exposure tools -> compare_scenarios -> validate_analysis

What happened recently to major portfolio companies?
  get_portfolio -> calculate_exposure -> current research tools -> validate_analysis

What was the latest one-year return for HDFC ELSS – Tax Saver Fund?
  search_financial_documents (fund-scoped Qdrant retrieval) -> agent answer with page citation
```

The configured Ollama model decides the actual next call after inspecting each result. Independent calls, such as holdings for several funds, may be requested together. Successful identical calls are cached within the request. A failing identical call can be retried once; global iteration and tool-call limits prevent loops. For scenario and current-research requests, the orchestrator runs `validate_analysis` on the final draft even when the model skips that tool; failed validation blocks the unsupported answer.

## Run

Create `backend/.env` from `backend/.env.example` and set at least:

```dotenv
OLLAMA_API_KEY=your-key
OLLAMA_MODEL=gemma4:31b
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_TIMEOUT_SECONDS=90
LOG_LEVEL=INFO
```

Create the key in your Ollama account. For direct cloud API requests, use a model name returned by `https://ollama.com/api/tags` (for example `gemma4:31b`), not the CLI-style `:cloud` alias. Select a model with tool-calling support. `OLLAMA_API_KEY` and `OLLAMA_MODEL` are required only for the chat endpoint. `DATABASE_URL`, `WEB_SEARCH_API_KEY`, and `MARKET_DATA_API_KEY` are reserved for the production adapters; the current mock tools do not pretend those adapters are active.

### Fund-document retrieval in the Django/React chat

The main agent calls the retrieval-only `search_financial_documents` tool for fund facts such as objectives, benchmarks, returns, SIP table values, and expense ratios. It resolves a single indexed fund name before querying Qdrant, refuses unscoped or conflicting fund searches, and returns the retrieved text with the exact PDF name and page. The existing Ollama agent writes the final response from those chunks; this bridge does not call a second answer-generating model or the VLM fallback.

Run Qdrant from the repository root (`docker compose up -d qdrant`), configure `QDRANT_URL` in `backend/.env`, and index newly added PDFs separately with `python manage.py index_factsheets` from `backend/`. Chat requests search the already-built collection and do not invoke Docling ingestion. The Django chat response includes an `answer_method` such as `agent_plus_rag`, `agent_plus_mfapi`, `agent_plus_rag_and_mfapi`, `agent_rag_no_evidence`, or `agent_only`; when document search ran it also returns `retrieved_chunks` plus page-specific `sources`. The React chat displays sources and method in the conversation and persists them with assistant messages, so they remain visible when reopening conversation history.

Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

Then open `http://127.0.0.1:8000/docs`.

## Chat API

```http
POST /api/chat
Content-Type: application/json

{
  "user_id": "USER001",
  "message": "Do my mutual funds overlap?",
  "conversation_context": []
}
```

Response shape:

```json
{
  "success": true,
  "answer": "...",
  "sources": [],
  "tool_trace": [
    {
      "call_id": "...",
      "tool": "get_portfolio",
      "activity": "Retrieved portfolio",
      "success": true,
      "duration_ms": 1.2,
      "error_code": null,
      "cached": false
    }
  ],
  "metadata": {
    "request_id": "...",
    "iterations": 3,
    "tool_calls": 2,
    "duration_ms": 1200,
    "data_errors": []
  }
}
```

`POST /agent/query` remains available with `{ "user_id": "...", "question": "..." }` for existing clients. `GET /tools` exposes the complete server-side schemas; model-facing schemas omit trusted identity and internal provider dependencies.

## Twelve Data market quotes

To enable the Market page and watchlist, add the following only to your local `backend/.env` file:

```dotenv
TWELVE_DATA_API_KEY=your-twelve-data-key
```

Restart Django after changing the file. The adapter requests quotes only for the five configured NSE companies and caches them for 60 seconds. It returns the provider's timestamp and labels the result as **latest available**; Indian exchange coverage may be end-of-day, so the application does not present these prices as real-time trading prices. A market-news summary and index feed remain intentionally unconfigured.

When Twelve Data cannot supply a configured company, the API uses the cookie-and-crumb Yahoo Finance technique from the selected community Indian Stock Market API project as a short-timeout fallback. It is not an official exchange feed, and the UI retains a community/Yahoo Finance source label and any provider delay. It requires no key, account, or frontend configuration.

## Django account access and private data

The React app uses the Django account API at `/api/v1/auth/`:

- `POST /signup/` creates an account and signs it in.
- `POST /login/` signs in with email and password.
- `POST /logout/` ends the session.
- `GET` and `PATCH /profile/` read or update the signed-in user's name.
- `GET /csrf/` initializes the CSRF cookie used by browser writes.

Authentication is a Django server-side session with CSRF protection. Portfolio imports, portfolio views, watchlists, chat history, and RAG jobs are scoped to the username generated by the server for the signed-in account; a `user_id` sent in a URL or body is ignored. Public fund discovery, NAV lookup, and calculators remain accessible without an account. Fund-disclosure uploads modify shared reference data and are restricted to staff accounts. Run the React app through the same-origin `/api` development proxy; production should use HTTPS and a same-origin reverse proxy so the session and CSRF cookies are not exposed to frontend JavaScript or sent cross-site.

For deployment, set `DJANGO_DEBUG=False`, a unique high-entropy `DJANGO_SECRET_KEY`, and `DJANGO_ALLOWED_HOSTS` in the environment. Session and CSRF cookies become Secure when debug is disabled. This adds the basic account/session flow, but does not yet include email verification, password reset, login throttling, or a managed account-recovery process; those are needed before treating it as a public production service. Data created before accounts existed is not automatically assigned to a new account.

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers narrow tool routing, current-research routing, sequential chaining, authenticated identity isolation, strict/malformed arguments, provider/database failures, missing and empty portfolios, unknown funds, source retention, validation blocking, Ollama request/response translation, NAV calculations, and ₹30,000 scenarios based on the actual portfolio. No live Ollama API call is needed for tests.

## Production adapters and extension

`DataStore` is the current repository boundary. `app/database.py` contains the existing SQLAlchemy PostgreSQL/pgvector schema scaffold; it is not silently activated by the agent. Replace repository/search/market provider implementations while keeping tool names and return shapes stable.

To add a tool, implement the focused function, add it to `FUNCTIONS`, add its category in `CATEGORY`, and—only if it has a clear intent—extend `ToolSelectionPolicy`. JSON input schemas and execution validation are generated automatically. Logs contain request/tool metadata and argument field names, not portfolio payloads, API keys, or full model reasoning.
