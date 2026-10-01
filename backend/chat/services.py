from typing import Any

from app.agent.ollama import answer_question


def run_chat(
    message: str,
    user_id: str,
    conversation_context: list[dict[str, str]] | None = None,
) -> dict:
    """Send a user question to the existing Agent."""
    return answer_question(
        question=message,
        user_id=user_id,
        conversation_context=conversation_context,
    )


def run_fundlens_rag(
    question: str,
    fund_scope: str | None = None,
    *,
    prompt_version: str = "v1",
    top_k: int = 5,
    usage_tracker: Any | None = None,
) -> dict:
    """Call the reusable FundLens RAG service from Django code.

    The import is deliberately lazy: the current chat API does not require
    the optional RAG stack unless a caller explicitly uses this service.
    """
    from fundlens_rag.service import answer_fundlens_question

    return answer_fundlens_question(
        question=question,
        fund_scope=fund_scope,
        prompt_version=prompt_version,
        top_k=top_k,
        usage_tracker=usage_tracker,
    )
