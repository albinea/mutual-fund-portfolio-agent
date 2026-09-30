from app.agent.gemini import answer_question


def run_chat(message: str, user_id: str) -> dict:
    """Send a user question to the existing Agent."""
    return answer_question(
        question=message,
        user_id=user_id,
    )
