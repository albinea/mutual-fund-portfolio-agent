"""Markdown table normalization and explicit row/column serialization."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterator


_SIP_LABELS = (
    ("Additional Benchmark Returns (%)", "additionalbenchmarkreturns"),
    ("Benchmark Returns (%)", "benchmarkreturns"),
    ("Total Amount Invested", "totalamountinvested"),
    ("Market Value as on August", "marketvalueasonaugust"),
    ("Returns (%)", "returns"),
)
_TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_NUMBER = re.compile(r"\d+(?:[,.]\d+)?")
_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)
_SIP_PERIOD = re.compile(r"\b(?P<years>\d+)\s*[- ]?\s*year\s+SIP\b", re.I)
_WORDS = re.compile(r"[a-z]+|\d+", re.I)
_QUERY_STOP_WORDS = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "give",
    "how", "i", "in", "is", "it", "me", "of", "on", "or", "please",
    "show", "tell", "the", "this", "to", "was", "what", "when", "which",
    "who", "with", "would", "do", "does", "did", "find", "provide",
    "happened", "information", "document", "documents",
    "fund", "scheme", "mutual", "sip", "year", "years", "august", "january",
    "february", "march", "april", "may", "june", "july", "september",
    "october", "november", "december", "lacs", "lac", "lakhs", "lakh",
}
_METRIC_STOP_WORDS = _QUERY_STOP_WORDS | {
    "hdfc", "medium", "long", "term", "regular", "plan", "growth", "option",
    "inception", "since", "1", "3", "5", "10", "15",
}


def make_tables_retrievable(markdown: str) -> str:
    """Repair known SIP row labels and add compact row-to-column text.

    Docling correctly finds the table grid in these factsheets, but their PDF
    font maps omit several letters from a few row labels. This keeps the
    original table values and layout, normalizes only familiar SIP metrics,
    and adds a plain-text mapping so embeddings and the answer model can see
    which value belongs to which period.
    """
    if not markdown:
        return markdown

    lines = markdown.splitlines()
    output: list[str] = []
    heading = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("#"):
            heading = line.lstrip("# ").strip()

        if not line.strip().startswith("|"):
            output.append(line)
            index += 1
            continue

        table_lines: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            table_lines.append(lines[index])
            index += 1

        table_lines = _normalize_sip_table(table_lines, heading)
        output.extend(table_lines)

        expanded_rows = _serialize_table(table_lines, heading)
        if expanded_rows:
            output.extend(
                [
                    "",
                    "**Table values by row and column (derived from the table above):**",
                    *expanded_rows,
                    "",
                ]
            )

    return "\n".join(output).strip() + "\n"


def answer_table_question(
    question: str,
    retrieved_chunks: list[dict[str, Any]],
) -> str | None:
    """Answer an unambiguous SIP table row/period lookup from retrieved text.

    This deliberately handles only an explicit ``N-year SIP`` column request
    and a uniquely matching metric row. Anything ambiguous falls through to
    the language model instead of guessing.
    """
    period = _SIP_PERIOD.search(question or "")
    if period is None:
        return None

    years = period.group("years")
    query_metric_terms = _terms(question, _METRIC_STOP_WORDS)
    if not query_metric_terms:
        return None

    query_terms = _terms(question, _QUERY_STOP_WORDS)
    candidates: list[tuple[float, float, int, str, str, str]] = []

    for source_index, chunk in enumerate(retrieved_chunks, start=1):
        text = str(chunk.get("text", ""))
        source_terms = _terms(text, set())
        source_overlap = (
            len(query_terms & source_terms) / len(query_terms)
            if query_terms
            else 0.0
        )
        if len(query_terms) >= 3 and source_overlap < 0.60:
            continue

        for _heading, label, header, value in _iter_table_values(text):
            if not re.search(
                rf"\b{re.escape(years)}\s*[- ]?\s*year\s+SIP\b",
                header,
                re.I,
            ):
                continue

            normalized = _normalize_sip_label(label)
            row_terms = _terms(normalized, _METRIC_STOP_WORDS)
            if not row_terms:
                continue

            question_month = _month_in(question)
            row_month = _month_in(normalized)
            if question_month and row_month and question_month != row_month:
                continue
            requested_years = re.findall(r"\b20\d{2}\b", question)
            if any(year not in text for year in requested_years):
                continue

            overlap = len(query_metric_terms & row_terms)
            score = overlap / len(query_metric_terms | row_terms)
            if score < 0.60 or not _NUMBER.search(value):
                continue

            candidates.append(
                (
                    score,
                    source_overlap,
                    source_index,
                    label,
                    header,
                    value.strip(),
                )
            )

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best = candidates[0]
    equally_relevant = [
        item
        for item in candidates
        if item[0] == best[0] and item[1] == best[1]
    ]
    if len({item[5] for item in equally_relevant}) > 1:
        return None

    _, _, source_index, label, header, value = best
    metric = _normalize_sip_label(label)
    metric = re.sub(r"\s*₹\s*in\s*(?:lacs?|lakhs?)\b.*$", "", metric, flags=re.I)
    unit = ""
    if re.search(r"₹\s*in\s*(?:lacs?|lakhs?)\b", label, re.I):
        unit = " lakh"

    display_value = f"₹{value}{unit}" if unit else value
    period_label = re.sub(r"\s+", " ", header).strip().lower()
    if metric.lower().startswith("market value"):
        metric = "Market Value"
    return (
        f"The table reports {metric.lower()} of {display_value} for the "
        f"{period_label}. [SOURCE {source_index}]"
    )


def _normalize_sip_table(table_lines: list[str], heading: str) -> list[str]:
    if "sip performance" not in heading.lower():
        return table_lines

    normalized_lines = list(table_lines)
    for index in range(2, len(normalized_lines)):
        cells = _split_table_row(normalized_lines[index])
        if len(cells) < 2 or _is_separator_row(cells):
            continue

        label = _normalize_sip_label(cells[0])
        if label != cells[0]:
            cells[0] = label
            normalized_lines[index] = _render_table_row(cells)

    return normalized_lines


def _normalize_sip_label(label: str) -> str:
    currency_position = label.find("₹")
    if currency_position >= 0:
        metric_text = label[:currency_position].strip()
        suffix = label[currency_position:].strip()
    else:
        metric_text = label.strip()
        suffix = ""

    compact = re.sub(r"[^a-z]", "", metric_text.lower())
    best_label = ""
    best_score = 0.0
    for canonical, target in _SIP_LABELS:
        score = SequenceMatcher(
            None,
            compact,
            target,
            autojunk=False,
        ).ratio()
        if score > best_score:
            best_label = canonical
            best_score = score

    if best_score < 0.78:
        return label

    return f"{best_label} {suffix}".strip()


def _serialize_table(table_lines: list[str], heading: str) -> list[str]:
    rows = [_split_table_row(row) for row in table_lines]
    rows = [row for row in rows if not _is_separator_row(row)]
    if len(rows) < 2:
        return []

    headers = rows[0]
    if not 2 <= len(headers) <= 12 or len(rows) > 41:
        return []

    summaries: list[str] = []
    title = heading.strip() or "Table"
    for row in rows[1:]:
        if len(row) != len(headers) or not row[0].strip():
            continue

        fields = [
            f"{headers[column]} = {row[column]}"
            for column in range(1, len(headers))
            if headers[column].strip() and row[column].strip()
        ]
        if fields:
            summaries.append(f"- {title} — {row[0]}: " + "; ".join(fields))

    return summaries


def _iter_markdown_tables(markdown: str) -> Iterator[tuple[str, list[str]]]:
    heading = ""
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("#"):
            heading = line.lstrip("# ").strip()

        if not line.strip().startswith("|"):
            index += 1
            continue

        table_lines: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            table_lines.append(lines[index])
            index += 1
        yield heading, table_lines


def _iter_table_values(markdown: str) -> Iterator[tuple[str, str, str, str]]:
    """Yield (table heading, row label, column heading, cell value) pairs."""
    for heading, table_lines in _iter_markdown_tables(markdown):
        rows = [_split_table_row(row) for row in table_lines]
        rows = [row for row in rows if not _is_separator_row(row)]
        if len(rows) < 2:
            continue

        headers = rows[0]
        for row in rows[1:]:
            if len(row) != len(headers) or not row[0].strip():
                continue
            for column in range(1, len(headers)):
                if headers[column].strip() and row[column].strip():
                    yield heading, row[0], headers[column], row[column]

    # Also read the row/column statements when retrieval returns that compact
    # block without the original Markdown grid.
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or " — " not in stripped:
            continue

        heading, details = stripped[2:].split(" — ", maxsplit=1)
        if ": " not in details:
            continue
        label, values = details.split(": ", maxsplit=1)
        for field in values.split("; "):
            if " = " not in field:
                continue
            header, value = field.split(" = ", maxsplit=1)
            yield heading, label, header, value


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _render_table_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(
        _TABLE_SEPARATOR_CELL.fullmatch(cell.replace(" ", ""))
        for cell in cells
    )


def _terms(text: str, stop_words: set[str]) -> set[str]:
    return {
        word.lower()
        for word in _WORDS.findall(text)
        if word.lower() not in stop_words and not word.isdigit()
    }


def _month_in(text: str) -> str | None:
    words = set(_WORDS.findall(text.lower()))
    return next((month for month in _MONTHS if month in words), None)
