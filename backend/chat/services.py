from app.agent.ollama import answer_question


def run_chat(
    message: str,
    user_id: str,
    conversation_context: list[dict] | None = None,
) -> dict:
    """Send a chat request to the existing agent orchestration layer."""
    try:
        return answer_question(
            question=message,
            user_id=user_id,
            conversation_context=conversation_context or [],
        )
    except Exception:
        return {
            "success": False,
            "error_code": "AGENT_UNAVAILABLE",
            "answer": "The agent could not complete the request.",
            "sources": [],
            "tool_trace": [],
            "metadata": {
                "iterations": 0,
                "tool_calls": 0,
            },
        }