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
