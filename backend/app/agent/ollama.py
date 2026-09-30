"""Ollama Cloud adapter for the provider-neutral orchestration loop."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from .orchestrator import AgentTurn, RequestedToolCall, SingleAgentOrchestrator, ToolResponse

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class OllamaSession:
    """Translate generic agent turns to Ollama's native chat/tool format."""

    def __init__(
        self,
        client: httpx.Client,
        model: str,
        system_prompt: str,
        question: str,
        context: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ):
        self.client = client
        self.model = model
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.messages.extend(
            {
                "role": "assistant" if item.get("role") in {"assistant", "model"} else "user",
                "content": item["content"],
            }
            for item in context
            if item.get("role") in {"user", "assistant", "model"} and item.get("content")
        )
        self.messages.append({"role": "user", "content": question})
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    def next_turn(self, tool_responses: list[ToolResponse] | None = None) -> AgentTurn:
        if tool_responses:
            self.messages.extend(
                {
                    "role": "tool",
                    "tool_name": item.name,
                    "content": json.dumps(item.result, separators=(",", ":"), default=str),
                }
                for item in tool_responses
            )
        response = self.client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": list(self.messages),
                "tools": self.tools,
                "stream": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama returned an invalid chat response.")
        self.messages.append(message)
        calls = []
        for index, tool_call in enumerate(message.get("tool_calls") or []):
            function = tool_call.get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise RuntimeError("Ollama returned a malformed tool call.")
            calls.append(RequestedToolCall(
                name=name,
                arguments=arguments,
                call_id=f"ollama-{len(self.messages)}-{index}",
            ))
        return AgentTurn(text=None if calls else str(message.get("content") or ""), tool_calls=calls)


class OllamaProvider:
    def __init__(self, api_key: str, model: str, base_url: str = "https://ollama.com", timeout: float = 90.0):
        self.model = model
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def start(self, *, system_prompt: str, question: str, conversation_context: list[dict], tools: list[dict]) -> OllamaSession:
        return OllamaSession(self.client, self.model, system_prompt, question, conversation_context, tools)

    def close(self) -> None:
        self.client.close()


def answer_question(question: str, user_id: str, conversation_context: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Run the single agent through Ollama Cloud."""
    api_key = os.getenv("OLLAMA_API_KEY")
    model = os.getenv("OLLAMA_MODEL")
    if not api_key or not model:
        return {
            "success": False,
            "error_code": "OLLAMA_NOT_CONFIGURED",
            "answer": "Set OLLAMA_API_KEY and OLLAMA_MODEL before using the agent endpoint.",
            "sources": [],
            "tool_trace": [],
            "metadata": {"iterations": 0, "tool_calls": 0},
        }
    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    except ValueError:
        timeout = 90.0
    provider = OllamaProvider(
        api_key=api_key,
        model=model,
        base_url=os.getenv("OLLAMA_BASE_URL", "https://ollama.com"),
        timeout=timeout,
    )
    try:
        return SingleAgentOrchestrator(provider).run(question, user_id, conversation_context)
    finally:
        provider.close()
