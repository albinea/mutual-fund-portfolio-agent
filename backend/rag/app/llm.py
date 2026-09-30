import json
import os

from langchain_ollama import ChatOllama

from app.schemas import LLMResponse


def get_llm():
    """
    Create the primary LLM.
    """

    model = os.getenv("OLLAMA_MODEL", "llama3.1")

    return ChatOllama(
        model=model,
        temperature=0,
    )


def generate_response(
    prompt: str,
    llm=None,
) -> LLMResponse:
    """
    Send the prompt to the LLM and validate the response with Pydantic.
    """

    if llm is None:
        llm = get_llm()

    response = llm.invoke(prompt)

    raw_content = response.content

    if isinstance(raw_content, list):
        raw_content = "".join(
            str(item) for item in raw_content
        )

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM returned invalid JSON."
        ) from exc

    return LLMResponse.model_validate(parsed)