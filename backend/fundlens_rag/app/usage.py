"""Per-answer and Streamlit-session model API usage accounting."""

from __future__ import annotations

import os
from typing import Any


_ROLE_RATE_PREFIX = {
    "answer": "OLLAMA_TEXT",
    "vision": "OLLAMA_VISION",
}


class UsageTracker:
    """Track model requests and provider-reported token counts, not user content."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, Any]] = {}

    def record_request(self, role: str, model: str) -> None:
        record = self._record(role, model)
        record["requests"] += 1

    def record_usage(
        self,
        role: str,
        model: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        record = self._record(role, model)
        if input_tokens is not None:
            record["input_tokens"] += input_tokens
            record["input_reports"] += 1
        if output_tokens is not None:
            record["output_tokens"] += output_tokens
            record["output_reports"] += 1

    def snapshot(self) -> list[dict[str, Any]]:
        return [dict(record) for record in self._records.values()]

    @staticmethod
    def merge_snapshots(
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Add this turn's counters to the current browser-session totals."""
        merged = {
            (record["role"], record["model"]): dict(record)
            for record in existing
        }
        for update in incoming:
            key = (update["role"], update["model"])
            if key not in merged:
                merged[key] = dict(update)
                continue
            for field in (
                "requests",
                "input_tokens",
                "output_tokens",
                "input_reports",
                "output_reports",
            ):
                merged[key][field] += update[field]
        return list(merged.values())

    @staticmethod
    def display_rows(records: list[dict[str, Any]]) -> list[dict[str, str | int]]:
        rows: list[dict[str, str | int]] = []
        for record in records:
            role = record["role"]
            input_display = _format_tokens(
                record["input_tokens"],
                record["input_reports"],
                record["requests"],
            )
            output_display = _format_tokens(
                record["output_tokens"],
                record["output_reports"],
                record["requests"],
            )
            cost = _cost_display(record)
            rows.append(
                {
                    "Purpose": "Answer model" if role == "answer" else "Vision fallback",
                    "Model": record["model"],
                    "API requests": record["requests"],
                    "Input tokens (reported)": input_display,
                    "Output tokens (reported)": output_display,
                    "Estimated cost (USD)": cost,
                }
            )
        return rows

    def _record(self, role: str, model: str) -> dict[str, Any]:
        key = (role, model)
        if key not in self._records:
            self._records[key] = {
                "role": role,
                "model": model,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "input_reports": 0,
                "output_reports": 0,
            }
        return self._records[key]


def get_langchain_token_counts(response: Any) -> tuple[int | None, int | None]:
    """Read usage from LangChain's Ollama AIMessage, with raw-metadata fallback."""
    usage = getattr(response, "usage_metadata", None)
    input_tokens = _nonnegative_int(_value(usage, "input_tokens"))
    output_tokens = _nonnegative_int(_value(usage, "output_tokens"))

    metadata = getattr(response, "response_metadata", None)
    if input_tokens is None:
        input_tokens = _nonnegative_int(_value(metadata, "prompt_eval_count"))
    if output_tokens is None:
        output_tokens = _nonnegative_int(_value(metadata, "eval_count"))
    return input_tokens, output_tokens


def get_ollama_token_counts(response: Any) -> tuple[int | None, int | None]:
    """Read prompt_eval_count/eval_count from the direct Ollama API response."""
    return (
        _nonnegative_int(_value(response, "prompt_eval_count")),
        _nonnegative_int(_value(response, "eval_count")),
    )


def _cost_display(record: dict[str, Any]) -> str:
    role = record["role"]
    prefix = _ROLE_RATE_PREFIX.get(role)
    if prefix is None:
        return "Unavailable"

    input_rate = _configured_rate(f"{prefix}_INPUT_USD_PER_1M_TOKENS")
    output_rate = _configured_rate(f"{prefix}_OUTPUT_USD_PER_1M_TOKENS")
    if input_rate is None or output_rate is None:
        return "Rates not configured"

    requests = record["requests"]
    if (
        requests == 0
        or record["input_reports"] != requests
        or record["output_reports"] != requests
    ):
        return "Token usage unavailable"

    cost = (
        record["input_tokens"] * input_rate
        + record["output_tokens"] * output_rate
    ) / 1_000_000
    return f"${cost:.8f}"


def _configured_rate(name: str) -> float | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    try:
        rate = float(raw_value)
    except ValueError:
        return None
    return rate if rate >= 0 else None


def _format_tokens(tokens: int, reports: int, requests: int) -> str:
    if reports == 0:
        return "Unavailable"
    rendered = f"{tokens:,}"
    if reports < requests:
        rendered += f" (reported by {reports}/{requests} calls)"
    return rendered


def _value(container: Any, key: str) -> Any:
    if isinstance(container, dict):
        return container.get(key)
    return getattr(container, key, None)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None
