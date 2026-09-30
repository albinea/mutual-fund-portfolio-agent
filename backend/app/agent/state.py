"""Per-request state for the single portfolio orchestration agent."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    """Safe, user-visible activity metadata (never model reasoning or payloads)."""

    call_id: str
    tool: str
    activity: str
    success: bool
    duration_ms: float
    error_code: str | None = None
    cached: bool = False


class AgentState(BaseModel):
    """Structured working memory for exactly one user request."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    original_question: str
    conversation_context: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    iterations: int = 0
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    tool_results: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    portfolio_data: dict[str, Any] | None = None
    fund_data: dict[str, dict[str, Any]] = Field(default_factory=dict)
    company_data: dict[str, Any] = Field(default_factory=dict)
    rag_results: list[dict[str, Any]] = Field(default_factory=list)
    web_results: list[dict[str, Any]] = Field(default_factory=list)
    analysis_results: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)

    def record_result(self, tool: str, result: dict[str, Any]) -> None:
        self.tool_results.setdefault(tool, []).append(result)
        if not result.get("success", True):
            self.errors.append(
                {
                    "tool": tool,
                    "error_code": result.get("error_code", "TOOL_FAILURE"),
                    "message": result.get("message", "Tool failed."),
                }
            )
        elif tool == "get_portfolio":
            self.portfolio_data = result
        elif tool in {"get_fund_holdings", "get_mutual_fund_details", "get_historical_performance"}:
            fund_id = str(result.get("fund_id", len(self.fund_data)))
            self.fund_data[fund_id] = result
        elif tool in {"calculate_exposure", "research_company", "get_market_data", "search_company_news"}:
            self.company_data.setdefault(tool, []).append(result)
        elif tool == "search_financial_documents":
            self.rag_results.extend(result.get("results", []))
        elif tool.startswith(("calculate_", "simulate_", "compare_", "analyze_", "validate_")):
            self.analysis_results.setdefault(tool, []).append(result)
        if tool in {"web_search", "search_company_news", "get_market_data", "research_company"}:
            self.web_results.append(result)
        self._collect_sources(result)

    def _collect_sources(self, value: Any) -> None:
        candidates: list[dict[str, Any]] = []

        def walk(node: Any, key: str | None = None) -> None:
            if isinstance(node, dict):
                if key in {"source", "sources", "provenance"} and (
                    "name" in node or "url" in node or "source_name" in node
                ):
                    candidates.append(node)
                for child_key, child in node.items():
                    walk(child, child_key)
            elif isinstance(node, list):
                for child in node:
                    walk(child, key)

        walk(value)
        seen = {
            (item.get("name") or item.get("source_name"), item.get("url"), item.get("data_as_of"))
            for item in self.sources
        }
        for source in candidates:
            normalized = {
                "name": source.get("name") or source.get("source_name") or "Source",
                "url": source.get("url") or source.get("source_url"),
                "published_date": source.get("published_date"),
                "retrieved_at": source.get("retrieved_at"),
                "data_as_of": source.get("data_as_of"),
            }
            key = (normalized["name"], normalized["url"], normalized["data_as_of"])
            if key not in seen:
                seen.add(key)
                self.sources.append(normalized)
