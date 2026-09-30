from pathlib import Path

import yaml


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(version: str = "v1") -> str:
    """
    Load a versioned prompt from prompts/<version>.yaml.
    """

    prompt_file = PROMPTS_DIR / f"{version}.yaml"

    if not prompt_file.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_file}"
        )

    with open(prompt_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "prompt" not in config:
        raise ValueError(
            f"Prompt file {prompt_file} must contain a 'prompt' field."
        )

    return config["prompt"]


def build_prompt(
    question: str,
    context: str,
    version: str = "v1",
) -> str:
    """
    Build the final prompt using the retrieved RAG context.
    """

    template = load_prompt(version)

    return template.format(
        question=question,
        context=context,
    )