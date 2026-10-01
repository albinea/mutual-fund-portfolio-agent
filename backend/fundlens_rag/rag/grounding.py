"""Citation checks applied before a RAG answer is shown to a user."""

from __future__ import annotations

import re
from typing import Any


_SOURCE_LABEL = re.compile(r"\[\s*SOURCE\s+(\d+)\s*\]", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_NUMBER = re.compile(r"\d+(?:[,.]\d+)?")
_STOP_WORDS = {
    "a", "about", "an", "and", "are", "be", "by", "can", "do", "does",
    "for", "from", "give", "how", "i", "in", "is", "it", "me", "of", "on",
    "or", "please", "the", "this", "to", "what", "which", "who", "with", "you",
    "investment", "objective", "fund", "scheme", "mutual",
}
_MIN_QUERY_TERM_OVERLAP = 0.60


class GroundingError(ValueError):
    """Raised when an answer cannot be supported by its cited chunks."""


def cited_chunks(
    answer: str,
    retrieved_chunks: list[dict[str, Any]],
    question: str,
) -> list[tuple[int, dict[str, Any]]]:
    """Return verified chunks explicitly cited by an answer.

    An answer must cite at least one available ``[SOURCE n]`` label. For
    specific questions (three or more meaningful terms), one cited chunk must
    also contain at least 60% of those terms. This prevents an answer about one
    named fund from being displayed with a citation to a different fund.
    """
    labels = _source_labels(answer)
    if not labels:
        raise GroundingError("The answer did not cite a retrieved source.")

    verified: list[tuple[int, dict[str, Any]]] = []
    for label in labels:
        if label < 1 or label > len(retrieved_chunks):
            raise GroundingError(f"The answer cited unavailable SOURCE {label}.")

        chunk = retrieved_chunks[label - 1]
        if not str(chunk.get("text", "")).strip():
            raise GroundingError(f"SOURCE {label} does not contain document text.")
        if not all(chunk.get(field) for field in ("document", "page", "source_url")):
            raise GroundingError(f"SOURCE {label} lacks citation metadata.")

        verified.append((label, chunk))

    query_terms = _meaningful_terms(question)
    if len(query_terms) >= 3 and not any(
        _term_overlap(query_terms, str(chunk["text"])) >= _MIN_QUERY_TERM_OVERLAP
        for _, chunk in verified
    ):
        raise GroundingError(
            "The cited document does not match the specific subject of the question."
        )

    # A valid source label alone does not ground a numeric claim. The value
    # must also occur in at least one of the chunks cited by the answer.
    answer_numbers = _numbers(answer) - _numbers(question)
    source_numbers = {
        number
        for _, chunk in verified
        for number in _numbers(str(chunk["text"]))
    }
    if answer_numbers and not answer_numbers.issubset(source_numbers):
        raise GroundingError("The answer includes a value not found in its cited source.")

    return verified


def ground_answer(
    answer: str,
    retrieved_chunks: list[dict[str, Any]],
    question: str,
) -> tuple[str, list[tuple[int, dict[str, Any]]]]:
    """Validate an answer and add a citation only when evidence is unambiguous.

    Models occasionally omit a required source label. In that case, the app
    can recover only when one retrieved chunk is a clear lexical match for the
    question and contains every numeric value stated in the answer. A model
    supplied but invalid label is never silently replaced.
    """
    if _source_labels(answer):
        return answer, cited_chunks(answer, retrieved_chunks, question)

    query_terms = _meaningful_terms(question)
    page_groups: dict[
        tuple[str, int, str], list[tuple[int, dict[str, Any]]]
    ] = {}
    for index, chunk in enumerate(retrieved_chunks, start=1):
        if not str(chunk.get("text", "")).strip():
            continue
        if not all(chunk.get(field) for field in ("document", "page", "source_url")):
            continue

        key = (str(chunk["document"]), int(chunk["page"]), str(chunk["source_url"]))
        page_groups.setdefault(key, []).append((index, chunk))

    candidates = [
        (
            chunks,
            _term_overlap(
                query_terms,
                "\n".join(str(chunk["text"]) for _, chunk in chunks),
            ),
        )
        for chunks in page_groups.values()
    ]

    if not candidates:
        raise GroundingError("No retrieved source is available for the answer.")

    chunks, overlap = max(candidates, key=lambda candidate: candidate[1])
    if len(query_terms) < 3 or overlap < _MIN_QUERY_TERM_OVERLAP:
        raise GroundingError("The answer did not cite a matching retrieved source.")

    # Numbers already present in the question (for example a date requested
    # by the user) are not new factual claims. Only validate values introduced
    # by the answer against the source text.
    answer_numbers = _numbers(answer) - _numbers(question)
    source_numbers = _numbers("\n".join(str(chunk["text"]) for _, chunk in chunks))
    if answer_numbers and not answer_numbers.issubset(source_numbers):
        raise GroundingError("The answer includes a value not found in its source.")

    labels = " ".join(f"[SOURCE {index}]" for index, _ in chunks)
    return f"{answer.rstrip()} {labels}", chunks


def _source_labels(answer: str) -> list[int]:
    """Extract source labels in answer order without duplicates."""
    labels: list[int] = []
    for match in _SOURCE_LABEL.finditer(answer):
        label = int(match.group(1))
        if label not in labels:
            labels.append(label)
    return labels


def _meaningful_terms(text: str) -> set[str]:
    return {
        word
        for word in _WORD.findall(text.lower())
        if len(word) > 2 and word not in _STOP_WORDS
    }


def _term_overlap(query_terms: set[str], source_text: str) -> float:
    source_terms = set(_WORD.findall(source_text.lower()))
    return len(query_terms & source_terms) / len(query_terms)


def _numbers(text: str) -> set[str]:
    """Return canonical numeric values, excluding citation-label numbers."""
    without_labels = _SOURCE_LABEL.sub("", text)
    return {match.replace(",", "") for match in _NUMBER.findall(without_labels)}
