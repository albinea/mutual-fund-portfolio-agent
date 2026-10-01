FundLens-RAG/
│
├── app/
│   ├── __init__.py
│   ├── streamlit_app.py
│   ├── llm.py
│   ├── prompts.py
│   ├── fallback.py
│   ├── logging_config.py
│   └── schemas.py
│
├── ingestion/
│   ├── __init__.py
│   ├── pdf_parser.py
│   ├── chunker.py
│   └── ingest.py
│
├── rag/
│   ├── __init__.py
│   ├── embeddings.py
│   ├── vector_store.py
│   ├── retriever.py
│   └── citations.py
│
├── prompts/
│   └── v1.yaml
│
├── evaluation/
│   ├── dataset.yaml
│   ├── evaluate.py
│   └── results.json
│
├── data/
│   └── documents/
│       ├── factsheets/
│       ├── annual_reports/
│       └── announcements/
│
├── qdrant_data/
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md

## Table-aware PDF ingestion

FundLens converts each factsheet to page-aware Markdown with Docling before
creating embeddings. Markdown files are saved in `data/markdown/`, while the
same page-aware Markdown is chunked and indexed for RAG retrieval.

The local Docling layout and table-recognition artifacts must be downloaded
once before starting the application:

```bash
cd backend/rag
../.venv/bin/docling-tools models download layout tableformer --output-dir docling_models
```

The app uses `docling_models/` by default. Set `DOCLING_ARTIFACTS_PATH` when
the artifacts are stored elsewhere. OCR is disabled for the bundled,
text-based factsheets; scanned PDFs require separately provisioning an OCR
model and enabling OCR in `ingestion/pdf_parser.py`.

Tables are retained intact in Markdown and also expanded into row/column
statements for retrieval. Common SIP performance labels affected by missing
PDF font glyphs are normalized without changing their numeric cells. For an
unambiguous question that specifies both a SIP period and a table metric, the
app reads the matching cell directly and verifies that the cited chunk
contains its value. The table-aware index uses a new Qdrant collection and
rebuilds the next time factsheets are indexed from the app.

Docling prefers the first CUDA GPU visible to the Streamlit process. Set
`DOCLING_DEVICE=cpu` to force CPU processing or `DOCLING_DEVICE=auto` to use
CUDA when available and otherwise fall back to CPU. The sidebar reports the
selected device. CUDA requires an NVIDIA driver visible inside the same
environment that starts Streamlit; the installed PyTorch build includes CUDA
12.8 support.

## On-demand Ollama Cloud vision fallback

The visual fallback is not used for normal answers. It runs only when the
regular answer is withheld/low-confidence or fails citation grounding, and
only after retrieval has supplied one or more local PDF page candidates. It
renders up to `OLLAMA_VISION_MAX_PAGES` distinct candidate pages in memory and
sends them to `OLLAMA_VISION_MODEL` (default `qwen3-vl:235b-cloud`) for an
evidence-only transcription. The normal text model then answers from that
transcription alone. Source name, page number, and URL continue to come from
the retrieved PDF metadata; visual model output cannot set citation metadata.
The resulting answer is grounded again and its confidence is capped at 65%.

For direct Ollama Cloud API access, set `OLLAMA_BASE_URL=https://ollama.com`
and configure `OLLAMA_API_KEY` in the backend environment, not in browser code
or source control. The fallback is skipped safely if cloud credentials are
missing, the page cannot be resolved locally, or the visual extraction cannot
be verified. Since only retrieved candidate pages can be inspected, a total
retrieval miss still requires a separate page-discovery fallback.

## Retrieval diagnostics and lenient answer display

The Streamlit sidebar enables **Show unverified drafts (lenient mode)** by
default. When grounding rejects a generated answer, the app displays it as an
unverified draft, keeps confidence at 0%, strips model-generated source labels,
and does not list it as a verified citation. Turn the option off to retain the
strict abstention behavior. The expanded **Retrieved chunks** panel shows the
exact top-five text chunks, document, PDF page, and retrieval score for every
question, including an explicit empty state when retrieval returns no chunks.

The answer view identifies whether the final answer came from RAG alone or
used the visual fallback. It reports API call counts and provider-reported
input/output tokens separately for the answer model and vision model, both
for the current answer and cumulatively for the current Streamlit browser
session. These counters contain usage only (not prompts or answers) and are
not persisted after the session ends. Ollama's rates can vary by model, so the
cost column stays unavailable until model-specific rates are configured in
`backend/.env` as USD per million tokens:

```dotenv
OLLAMA_TEXT_INPUT_USD_PER_1M_TOKENS=
OLLAMA_TEXT_OUTPUT_USD_PER_1M_TOKENS=
OLLAMA_VISION_INPUT_USD_PER_1M_TOKENS=
OLLAMA_VISION_OUTPUT_USD_PER_1M_TOKENS=
```

Enter the current input/output rates for the selected answer and vision models.
When usage is incomplete or a rate is missing, cost is left unavailable rather
than estimated from an assumed price. The displayed estimate uses Ollama's
reported prompt/evaluation token counts; provider billing may differ for
image inputs or cached tokens.

## Fund-scoped retrieval

Fund names are extracted from scheme headings and attached to page chunks;
continuation pages inherit the current scheme heading, while pages with
multiple scheme headings are left unassigned rather than guessed. The UI can
detect a canonical fund name in the question or use the sidebar fund selector.
Qdrant filters by `fund_name` before ranking the top chunks. If the fund is
missing or ambiguous, the app asks for a selection and does not search across
all funds. The `fundlens_documents_v6` collection carries this metadata. On
migration, existing JSON chunks are enriched in memory and indexed without
rewriting their Markdown or JSON files; older Qdrant collections are retained.
