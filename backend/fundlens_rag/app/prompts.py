from pathlib import Path

import yaml

from fundlens_rag.paths import RAG_PROJECT_ROOT

PROMPTS_DIR = RAG_PROJECT_ROOT / "prompts"


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

    if not config:
        raise ValueError(
            f"Prompt file {prompt_file} must contain prompt content."
        )

    # Support a single legacy ``prompt`` template as well as the clearer
    # system/user format used by the versioned prompt files.
    if "prompt" in config:
        template = config["prompt"]
    elif "system" in config and "user" in config:
        template = f"{config['system'].strip()}\n\n{config['user'].strip()}"
    else:
        raise ValueError(
            f"Prompt file {prompt_file} must contain either a 'prompt' field "
            "or both 'system' and 'user' fields."
        )

    if not isinstance(template, str):
        raise ValueError(f"Prompt content in {prompt_file} must be text.")

    return template


def build_prompt(
    question: str,
    context: str,
    version: str = "v1",
) -> str:
    """
    Build the final prompt using the retrieved RAG context.
    """

    template = load_prompt(version)

    # Only these two placeholders are dynamic. ``str.format`` would also
    # interpret the literal braces in the required JSON response example.
    return template.replace("{question}", question).replace("{context}", context)
