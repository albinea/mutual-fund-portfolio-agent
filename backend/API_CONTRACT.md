# Mutual Fund Portfolio Agent API Contract

Base URL in development: `http://127.0.0.1:8000/api/v1/`

Interactive Swagger documentation: `http://127.0.0.1:8000/api/docs/`

## Common response envelope

All non-chat endpoints use this shape:

```json
{
  "success": true,
  "data": {},
  "sources": [],
  "message": null
}
```

Errors use:

```json
{
  "success": false,
  "error_code": "INVALID_INPUT",
  "message": "A human-readable explanation."
}
```

The frontend must read page-specific fields from `data`. It must not calculate financial values from raw holdings.

## Available now

| Route | Purpose |
| --- | --- |
| `GET /portfolio/summary/?user_id=USER001` | Total invested/current value and portfolio counts |
| `GET /portfolio/holdings/?user_id=USER001` | Filterable fund holdings table |
| `GET /portfolio/allocation/?user_id=USER001&group_by=sector` | Fund/category/sector/company allocation |
| `GET /portfolio/overlap/?user_id=USER001` | Overlapping companies and portfolio exposure |
| `GET /funds/` | Fund explorer over the configured fund master |
| `GET /funds/{fund_id}/` | Fund detail fields available in the data source |
| `POST /funds/compare/` | Compare 2-5 fund IDs |
| `POST /calculators/sip/` | Deterministic SIP projection |
| `POST /calculators/expected-wealth/` | Deterministic wealth projection |
| `GET /companies/{company_id}/fund-exposure/?user_id=USER001` | Company-to-fund-to-portfolio exposure |
| `GET/POST/DELETE /watchlist/` | User-scoped development watchlist |
| `POST /chat/` | Agent chat with MySQL-backed conversation memory |

## Not configured yet

The following routes are intentionally present for frontend parallel development. They return HTTP `501` with `error_code: DATA_NOT_CONFIGURED` until their data service is implemented:

- `POST /uploads/` and `POST /portfolio/import/` - secure file storage, parsing, and normalized portfolio imports
- `GET /portfolio/changes/` and change explanation - historical portfolio snapshots and factsheet evidence
- rolling returns, manager commentary, and fund discovery - complete NAV-return and factsheet datasets
- market overview and market summary - live market and verified-news providers
- `POST /exports/excel/` - generated-file storage and signed download URLs

## Important integration notes

- `user_id` is a development identity. It will be replaced by authenticated Django user identity before deployment.
- Chat returns its existing top-level agent response (`answer`, `sources`, `tool_trace`, `metadata`, and `conversation_id`) for backwards compatibility.
- `return_3y`, manager tenure, and risk-adjusted rating are `null` when the current verified data source does not provide them. The frontend should display "Not available" and must not invent a value.
- Calculator results are projections only. Always show the returned disclaimer.
