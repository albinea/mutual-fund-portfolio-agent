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
- Public NAV analytics: `get_nav_history`, `calculate_cagr`, `calculate_volatility`, `calculate_drawdown`, `compare_funds`

Current adapter status matters: portfolio/fund calculations use timestamped mock JSON; NAV tools use the public MF API; the vector store and general web-search provider explicitly report that they are unconfigured. The agent is instructed to surface those limitations and never substitute invented evidence.

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

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests -q
```

The suite covers narrow tool routing, current-research routing, sequential chaining, authenticated identity isolation, strict/malformed arguments, provider/database failures, missing and empty portfolios, unknown funds, source retention, validation blocking, Ollama request/response translation, NAV calculations, and ₹30,000 scenarios based on the actual portfolio. No live Ollama API call is needed for tests.

## Production adapters and extension

`DataStore` is the current repository boundary. `app/database.py` contains the existing SQLAlchemy PostgreSQL/pgvector schema scaffold; it is not silently activated by the agent. Replace repository/search/market provider implementations while keeping tool names and return shapes stable.

To add a tool, implement the focused function, add it to `FUNCTIONS`, add its category in `CATEGORY`, and—only if it has a clear intent—extend `ToolSelectionPolicy`. JSON input schemas and execution validation are generated automatically. Logs contain request/tool metadata and argument field names, not portfolio payloads, API keys, or full model reasoning.
