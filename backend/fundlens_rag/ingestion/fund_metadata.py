"""Discover canonical fund names and attach section context to page chunks."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Iterable


_HEADING = re.compile(r"^\s{0,3}#{1,3}\s+(.+?)\s*$")
_FUND_TITLE = re.compile(
    r"^(?:[A-Z][A-Za-z0-9&'()-]*|[A-Z0-9]{2,})"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&'()-]*|[A-Z0-9]{2,}|\d+)){1,4}"
    r"(?:\s+.+)?\s+\b(?:Fund(?:\s+of\s+Funds?)?|ETF|FOF|BeES)$",
    re.IGNORECASE,
)
_GLOBAL_SECTION_HEADINGS = {
    "contents",
    "fund details annexure",
    "fund manager",
    "glossary",
    "how to read factsheet",
    "macroeconomic update",
    "nature of scheme",
    "performance details of schemes managed by respective fund managers",
}


def extract_fund_names(text: str) -> list[str]:
    """Return unique mutual-fund, ETF, FOF, and BeES names in headings."""
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _HEADING.match(line)
        if not match:
            continue
        name = _clean_fund_heading(match.group(1))
        if not name:
            continue
        key = _normalize_name(name)
        if key not in seen:
            names.append(name)
            seen.add(key)
    return names


def list_known_funds(
    markdown_directory: str | Path,
    chunks_directory: str | Path | None = None,
) -> list[str]:
    """Build a small fund-name catalog from existing Markdown and chunk files."""
    names: dict[str, str] = {}
    markdown_directory = Path(markdown_directory)
    if markdown_directory.exists():
        for path in sorted(markdown_directory.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for name in extract_fund_names(text):
                names.setdefault(_normalize_name(name), name)

    if chunks_directory is not None:
        chunks_directory = Path(chunks_directory)
        if chunks_directory.exists():
            for path in sorted(chunks_directory.glob("*.json")):
                try:
                    chunks = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(chunks, list):
                    continue
                for chunk in chunks:
                    if not isinstance(chunk, dict):
                        continue
                    fund_name = str(chunk.get("fund_name") or "").strip()
                    if _clean_fund_heading(fund_name):
                        names.setdefault(_normalize_name(fund_name), fund_name)
                    for name in extract_fund_names(str(chunk.get("text", ""))):
                        names.setdefault(_normalize_name(name), name)

    return sorted(names.values(), key=str.casefold)


def resolve_fund_name(question: str, known_funds: Iterable[str]) -> str | None:
    """Resolve an explicitly named fund; return None if absent or ambiguous.

    Matching is case- and punctuation-insensitive. Omitting the "HDFC" prefix
    is accepted, but the resolver deliberately avoids guessing from the topic
    of a question.
    """
    normalized_question = _normalize_name(question)
    occurrences: list[tuple[str, int, int]] = []
    for fund_name in known_funds:
        normalized_name = _normalize_name(fund_name)
        aliases = {normalized_name}
        if normalized_name.startswith("hdfc "):
            aliases.add(normalized_name.removeprefix("hdfc "))

        for alias in aliases:
            if not alias:
                continue
            pattern = re.compile(
                rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            )
            occurrences.extend(
                (fund_name, match.start(), match.end())
                for match in pattern.finditer(normalized_question)
            )

    # A shorter scheme name can be a prefix of a longer one (for example,
    # "HDFC Gold ETF" inside "HDFC Gold ETF Fund of Fund"). Ignore the
    # contained occurrence, but keep a separately mentioned shorter fund.
    matches = {
        fund_name
        for fund_name, start, end in occurrences
        if not any(
            other_start <= start
            and other_end >= end
            and (other_start, other_end) != (start, end)
            for _other_name, other_start, other_end in occurrences
        )
    }

    if not matches:
        return None

    if len(matches) != 1:
        return None
    return next(iter(matches))


def assign_fund_names_to_pages(
    page_texts: Iterable[tuple[int, str]],
) -> list[tuple[int, str, str | None]]:
    """Carry a single scheme heading over its continuation pages.

    A page containing multiple distinct scheme headings is treated as shared
    material rather than incorrectly attributed to whichever fund came first.
    """
    assigned: list[tuple[int, str, str | None]] = []
    current_fund: str | None = None

    for page_number, page_text in sorted(page_texts, key=lambda item: item[0]):
        page_funds = extract_fund_names(page_text)
        if len(page_funds) == 1:
            current_fund = page_funds[0]
        elif len(page_funds) > 1 or _has_global_section_heading(page_text):
            current_fund = None

        assigned.append((page_number, page_text, current_fund))

    return assigned


def attach_fund_names_to_chunks(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add fund context to legacy chunk JSON in memory without rewriting it."""
    by_document: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for chunk in chunks:
        document = str(chunk.get("document") or "")
        try:
            page_number = int(chunk.get("page"))
        except (TypeError, ValueError):
            page_number = -1
        by_document.setdefault(document, {}).setdefault(page_number, []).append(chunk)

    fund_for_page: dict[tuple[str, int], str | None] = {}
    for document, pages in by_document.items():
        page_texts = [
            (
                page_number,
                "\n\n".join(str(chunk.get("text", "")) for chunk in page_chunks),
            )
            for page_number, page_chunks in pages.items()
        ]
        for page_number, _text, fund_name in assign_fund_names_to_pages(page_texts):
            fund_for_page[(document, page_number)] = fund_name

    enriched: list[dict[str, Any]] = []
    for chunk in chunks:
        result = dict(chunk)
        document = str(chunk.get("document") or "")
        try:
            page_number = int(chunk.get("page"))
        except (TypeError, ValueError):
            page_number = -1
        result["fund_name"] = fund_for_page.get((document, page_number))
        enriched.append(result)
    return enriched


def _clean_fund_heading(heading: str) -> str | None:
    name = re.sub(r"\s+", " ", html.unescape(heading)).strip(" #\t")
    if _normalize_name(name) == "name of mutual fund":
        return None
    if _FUND_TITLE.fullmatch(name):
        return name
    return None


def _normalize_name(value: str) -> str:
    normalized = html.unescape(value).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _has_global_section_heading(text: str) -> bool:
    for line in text.splitlines():
        match = _HEADING.match(line)
        if not match:
            continue
        heading = _normalize_name(html.unescape(match.group(1)))
        if heading in _GLOBAL_SECTION_HEADINGS:
            return True
    return False
