"""Explicit, bounded single-agent tool orchestration loop."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from .policy import ToolSelectionPolicy
from .state import AgentState, ToolCallTrace
from .tool_registry import TOOLS, call_tool, registry

log = logging.getLogger("portfolio.agent")

SYSTEM_PROMPT = """You are the one orchestration agent for a mutual-fund portfolio intelligence system.
Use only registered tools and structured outputs. Never calculate portfolio percentages, exposure,
overlap, returns, volatility, tax, or scenario allocations yourself when a deterministic tool exists.
Call only tools necessary for the question and inspect each result before choosing the next call.
Portfolio identity is securely bound; never request or supply a user_id.

Use internal document search for factsheets, disclosures, reports, and historical documents. Use
web/news/market tools for explicitly current or recent questions. Never describe stale data as live;
state material data-as-of dates. If a tool fails, retry only when sensible, choose another available
tool, or explain the limitation. Never invent figures, evidence, URLs, or tool results. For scenarios,
present alternatives, assumptions, and risks rather than promising future returns. Call
validate_analysis before completing complex scenario or externally sourced analysis.

The final answer must be concise and evidence-based. Cite only source metadata returned by tools.
Do not reveal private chain-of-thought. You may summarize activities, assumptions, errors, and
evidence. This is decision support, not a guarantee of investment performance.
"""

ACTIVITY = {
    "get_portfolio": "Retrieved portfolio", "get_fund_holdings": "Retrieved fund holdings",
    "get_mutual_fund_details": "Retrieved fund details", "calculate_exposure": "Calculated company exposure",
    "calculate_fund_overlap": "Calculated fund overlap", "calculate_sector_exposure": "Calculated sector exposure",
    "calculate_portfolio_risk": "Calculated portfolio risk", "search_financial_documents": "Searched financial documents",
    "web_search": "Searched current web information", "search_company_news": "Searched company news",
    "get_market_data": "Retrieved market data", "research_company": "Researched company",
    "simulate_allocation": "Simulated allocation", "compare_scenarios": "Compared scenarios",
    "calculate_tax_impact": "Calculated tax impact", "analyze_goal": "Analyzed goal",
    "validate_analysis": "Validated analysis", "get_nav_history": "Retrieved NAV history",
    "calculate_cagr": "Calculated CAGR", "calculate_volatility": "Calculated volatility",
    "calculate_drawdown": "Calculated drawdown", "compare_funds": "Compared funds",
}


@dataclass
class RequestedToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class ToolResponse:
    call_id: str
    name: str
    result: dict[str, Any]


@dataclass
class AgentTurn:
    text: str | None = None
    tool_calls: list[RequestedToolCall] = field(default_factory=list)


class AgentSession(Protocol):
    def next_turn(self, tool_responses: list[ToolResponse] | None = None) -> AgentTurn: ...


class AgentProvider(Protocol):
    def start(self, *, system_prompt: str, question: str, conversation_context: list[dict[str, str]], tools: list[dict[str, Any]]) -> AgentSession: ...


class SingleAgentOrchestrator:
    """Run one model session that may sequentially call many existing tools."""

    def __init__(self, provider: AgentProvider, *, max_iterations: int = 12, max_tool_calls: int = 20, max_retries_per_call: int = 1, policy: ToolSelectionPolicy | None = None):
        self.provider = provider
        self.max_iterations = max_iterations
        self.max_tool_calls = max_tool_calls
        self.max_retries_per_call = max_retries_per_call
        self.policy = policy or ToolSelectionPolicy()

    def run(self, question: str, user_id: str, conversation_context: list[dict[str, str]] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        state = AgentState(user_id=user_id, original_question=question, conversation_context=conversation_context or [])
        allowed = self.policy.select(question, set(TOOLS))
        tool_specs = registry(for_model=True, names=allowed)
        try:
            session = self.provider.start(system_prompt=SYSTEM_PROMPT, question=question, conversation_context=state.conversation_context, tools=tool_specs)
            pending: list[ToolResponse] | None = None
            total_calls = 0
            cache: dict[str, dict[str, Any]] = {}
            attempts: dict[str, int] = {}
            for iteration in range(1, self.max_iterations + 1):
                state.iterations = iteration
                turn = session.next_turn(pending)
                pending = None
                if turn.tool_calls:
                    responses: list[ToolResponse] = []
                    for requested in turn.tool_calls:
                        if total_calls >= self.max_tool_calls:
                            result = self._error("TOOL_LIMIT_REACHED", "The request exceeded the safe tool-call limit.")
                            responses.append(ToolResponse(requested.call_id, requested.name, result))
                            state.record_result(requested.name, result)
                            continue
                        total_calls += 1
                        call_key = self._cache_key(requested)
                        cached = call_key in cache and cache[call_key].get("success", True)
                        call_started = time.perf_counter()
                        if requested.name not in allowed:
                            result = self._error("TOOL_NOT_ALLOWED", "This tool is not relevant to the current request.")
                        elif cached:
                            result = cache[call_key]
                        elif attempts.get(call_key, 0) > self.max_retries_per_call:
                            result = self._error("RETRY_LIMIT_REACHED", "The same failing tool call was not retried again.")
                        else:
                            attempts[call_key] = attempts.get(call_key, 0) + 1
                            result = call_tool(requested.name, requested.arguments, user_id=state.user_id)
                            if result.get("success", True):
                                cache[call_key] = result
                        duration = round((time.perf_counter() - call_started) * 1000, 2)
                        state.tool_calls.append(ToolCallTrace(
                            call_id=requested.call_id,
                            tool=requested.name,
                            activity=ACTIVITY.get(requested.name, requested.name.replace("_", " ").capitalize()),
                            success=bool(result.get("success", True)),
                            duration_ms=duration,
                            error_code=result.get("error_code"),
                            cached=cached,
                        ))
                        state.record_result(requested.name, result)
                        responses.append(ToolResponse(requested.call_id, requested.name, result))
                    pending = responses
                    continue
                answer = (turn.text or "").strip() or "I could not produce an evidence-based answer from the available results."
                if "validate_analysis" in allowed:
                    self._validate_final_answer(state, answer)
                validations = state.tool_results.get("validate_analysis", [])
                if validations and not validations[-1].get("valid", False):
                    return self._response(state, "The analysis did not pass evidence validation, so no unsupported conclusion is being returned.", started, success=False, error_code="ANALYSIS_VALIDATION_FAILED")
                return self._response(state, answer, started, success=True)
            return self._response(state, "I could not complete the analysis within the safe orchestration limit. Please narrow the question and try again.", started, success=False, error_code="ITERATION_LIMIT_REACHED")
        except Exception:
            log.exception("agent request failed", extra={"request_id": state.request_id, "user_id": user_id})
            return self._response(state, "The analysis agent could not complete this request. No missing financial data has been inferred.", started, success=False, error_code="AGENT_FAILURE")

    @staticmethod
    def _cache_key(call: RequestedToolCall) -> str:
        return f"{call.name}:{json.dumps(call.arguments, sort_keys=True, separators=(',', ':'), default=str)}"

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"success": False, "error_code": code, "message": message, "source": None}

    @staticmethod
    def _validate_final_answer(state: AgentState, answer: str) -> None:
        """Run the deterministic validation gate even when the model skips it."""
        lowered = answer.casefold()
        safe_limitation = any(phrase in lowered for phrase in (
            "cannot provide a single company recommendation",
            "cannot provide specific investment advice",
            "can't provide a single company recommendation",
            "unable to recommend",
            "insufficient information",
            "could not retrieve",
            "data is unavailable",
        ))
        claims = [] if safe_limitation else [answer]
        sources = [] if not claims else [state.sources[0] if state.sources else {}]
        dates = [source["data_as_of"] for source in state.sources if source.get("data_as_of")]
        started = time.perf_counter()
        result = call_tool("validate_analysis", {
            "claims": claims,
            "sources": sources,
            "data_as_of_dates": dates or None,
        }, user_id=state.user_id)
        state.tool_calls.append(ToolCallTrace(
            call_id="final-answer-validation",
            tool="validate_analysis",
            activity=ACTIVITY["validate_analysis"],
            success=bool(result.get("success", True)) and bool(result.get("valid", False)),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_code=result.get("error_code") or (None if result.get("valid", False) else "VALIDATION_FAILED"),
            cached=False,
        ))
        state.record_result("validate_analysis", result)

    @staticmethod
    def _response(state: AgentState, answer: str, started: float, *, success: bool, error_code: str | None = None) -> dict[str, Any]:
        duration = round((time.perf_counter() - started) * 1000, 2)
        trace = [item.model_dump() for item in state.tool_calls]
        log.info("agent_request_completed", extra={
            "request_id": state.request_id, "user_id": state.user_id,
            "query_length": len(state.original_question), "selected_tools": [item["tool"] for item in trace],
            "iterations": state.iterations, "duration_ms": duration, "success": success,
                "response_length": len(answer),
        })
        response = {
            "success": success, "answer": answer, "sources": state.sources, "tool_trace": trace,
            "metadata": {"request_id": state.request_id, "iterations": state.iterations, "tool_calls": len(trace), "duration_ms": duration, "data_errors": state.errors},
        }
        if error_code:
            response["error_code"] = error_code
        return response
