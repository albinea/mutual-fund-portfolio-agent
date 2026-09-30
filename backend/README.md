# Mutual Fund Portfolio Intelligence Tool Layer

Python tool functions and a thin FastAPI surface for a single orchestrator agent. The tools do not depend on an LLM and return structured results, errors, and provenance. Mock data is the active adapter; PostgreSQL schema scaffolding is included for the next adapter.

## Run

```sh
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

Open `/docs` for the HTTP interface. Set `PYTHONPATH=backend` to import tools from the repository root. Tests are in `tests/` and run with `pytest` from this directory.

## Architecture and data flow

`app/tools/core.py` contains independent validated-by-input-contract functions. `app/schemas.py` defines shared Pydantic result contracts. `app/agent/tool_registry.py` exposes function names, descriptions, JSON-style input/output schemas, categories, and permissions; it does not implement agent planning. `app/api/main.py` maps suitable operations to HTTP endpoints. `app/database.py` defines PostgreSQL entities and optional pgvector embeddings.

`DataStore` reads JSON mock files and is the replaceable repository boundary. Replace its methods with SQLAlchemy repositories; inject external search and market providers through provider interfaces while keeping tool names and return shapes stable. API keys belong in server environment variables and are never returned by tools.

## Tools

Portfolio: `get_portfolio`, `get_fund_holdings`, `calculate_exposure`, `calculate_fund_overlap`, `calculate_sector_exposure`, `calculate_portfolio_risk`.

Knowledge: `search_financial_documents`, `get_mutual_fund_details`, `get_historical_performance`. Search and NAV history return explicit unavailable results until configured; no empty or invented evidence is substituted.

External research: `web_search`, `search_company_news`, `get_market_data`, `research_company`. Search provider is intentionally unconfigured. Mock market data is explicitly timestamped and delayed; provider replacement uses `MarketDataProvider`.

Analysis: `simulate_allocation`, `compare_scenarios`, `calculate_tax_impact`, `analyze_goal`, `validate_analysis`. Tax impact stays unavailable without tax lots and current rules. Goal analysis does not invent expected returns. Scenario tools compare evidence and do not rank an investment as best.

Every tool is available in `TOOLS` and can also be imported and called directly. Unknown tools and malformed calls return structured errors. Portfolio endpoints currently accept a user ID for local demonstration; production authentication must derive the user identity from verified auth context and enforce ownership before invoking these functions. Avoid logging portfolio payloads; call logs record tool, user ID, timing, status and source label, with financial arguments omitted.

## Dependencies and example workflow

`get_portfolio` and `get_fund_holdings` supply inputs to exposure, sector, overlap, and risk calculations. Scenario simulation composes current fund values with contributions, then recomputes fund, company, and sector composition. `research_company` combines market data, news, and document search and returns source records without recommendations.

Example for “I have ₹30,000 more to invest; compare allocations”:

```python
from app.agent.tool_registry import call_tool
p = call_tool("get_portfolio", {"user_id": "USER001"})
holdings = [call_tool("get_fund_holdings", {"fund_id": f["fund_id"]}) for f in p["funds"]]
exposure = call_tool("calculate_exposure", {"user_id": "USER001"})
overlap = call_tool("calculate_fund_overlap", {"user_id": "USER001"})
sectors = call_tool("calculate_sector_exposure", {"user_id": "USER001"})
risk = call_tool("calculate_portfolio_risk", {"user_id": "USER001"})
comparison = call_tool("compare_scenarios", {
  "user_id": "USER001", "additional_amount": 30000,
  "scenarios": [
    {"name": "Spread evenly", "allocation": {"F001": 10000, "F002": 10000, "F003": 10000}},
    {"name": "Add to flexi and mid cap", "allocation": {"F002": 15000, "F003": 15000}}
  ]
})
validated = call_tool("validate_analysis", {"claims": [], "sources": []})
```

The agent decides whether current web research is needed, chains these results, and explains assumptions. Historical performance is not a forecast. All mock figures are illustrative, not live recommendations.

## Mock data

`mock_data/` contains users, mutual funds, holdings, companies, market data, and news. Holdings preserve their disclosure date and source URL. Example sources are deliberately non-live `example.org` references. Configure production sources and attribution before user-facing use.
