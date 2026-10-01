FundLens now has a reusable Python package alongside the RAG assets:

```text
backend/
├── fundlens_rag/              # Reusable RAG service and implementation
│   ├── service.py             # Single UI-independent answer entry point
│   ├── app/                   # LLM, prompts, usage, and vision fallback
│   ├── ingestion/             # Docling parsing and table-aware chunking
│   └── rag/                   # Qdrant retrieval, grounding, and citations
├── chat/services.py           # Django adapter: run_fundlens_rag(...)
└── rag/                       # Prompts, PDFs, Markdown, and chunks
    ├── prompts/
    ├── evaluation/
    └── data/
```

The vector index is stored in the persistent Qdrant service, not in this tree.

The Streamlit app is still available at `fundlens_rag/app/streamlit_app.py`.
Both it and Django call `fundlens_rag.service.answer_fundlens_question()`;
the Django adapter is intentionally separate from the existing chat endpoint.
RAG imports use the `fundlens_rag` namespace so they cannot collide with the
main Django project's own `app` package.

The React chat uses the asynchronous API so long VLM fallback requests do not
hold an HTTP request open. Apply the database migration and run a worker beside
the Django server:

```bash
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py run_rag_worker
```

The UI submits `POST /api/v1/rag/jobs/`, receives a job ID immediately, and
polls `GET /api/v1/rag/jobs/<job_id>/` until it gets the result. The final
result contains the verified citations, retrieved chunk text and page
metadata used by the evidence panel, confidence, answer method, model usage,
and configured estimated cost. Jobs and results are stored in the Django
database. Run one worker process initially; scale workers after confirming
that the configured database supports the expected concurrency. The existing
synchronous `POST /api/v1/rag/answer/` endpoint remains available for clients
that need its direct-response contract, but long model calls can still exceed
their HTTP timeout.

Local PDF paths and source URLs are omitted from API responses. Ollama
credentials and model-rate settings stay in the server environment; they are
never returned to the client. The Django runtime dependencies are listed in
`backend/fundlens_rag/requirements.txt`. Docling/Torch are separate optional
dependencies for the one-shot ingestion task; they are not loaded by answer
requests. Both the Django API and standalone UI connect to the same Qdrant
server using `QDRANT_URL`; neither opens an embedded Qdrant data directory.

## Persistent Qdrant server

The repository's Compose setup includes a Qdrant server with a named
`qdrant_storage` volume, so vectors survive container restarts. From the
repository root, start it with:

```bash
docker compose up -d qdrant
```

When Django or Streamlit runs directly on the host, configure
`QDRANT_URL=http://127.0.0.1:6333` in the root `.env` (or backend environment).
If the backend later runs as a Compose service, use `QDRANT_URL=http://qdrant:6333`
on the private Compose network instead. The local Compose port is bound to
loopback and is intended for development; use a private/TLS-protected service
for shared or production deployments. `QDRANT_API_KEY` is optional and should
only be used with a protected/TLS endpoint.

The new server starts with an empty collection. From `backend/`, populate it
separately from chat requests with:

```bash
.venv/bin/python manage.py index_factsheets
```

This command indexes factsheets missing from Qdrant. Existing page-aware chunk
JSON files are reused; Docling is invoked only when a PDF has no cached chunk
file. The Django and Streamlit question paths only search the prepared
collection. Existing embedded data in `rag/qdrant_data/` is left untouched but
is no longer read by the application.

For the separate indexing environment, install
`fundlens_rag/ingestion-requirements.txt` and provision the Docling artifacts
described below. The normal Django web runtime does not need these heavy PDF
dependencies.

From the `backend/` directory, run the standalone UI and RAG tests with:

```bash
.venv/bin/streamlit run fundlens_rag/app/streamlit_app.py
.venv/bin/python -m unittest discover -s rag/tests -v
```

## Table-aware PDF ingestion

FundLens converts each factsheet to page-aware Markdown with Docling before
creating embeddings. Markdown files are saved in `data/markdown/`, while the
same page-aware Markdown is chunked and indexed for RAG retrieval.

The local Docling layout and table-recognition artifacts must be downloaded
once before indexing PDFs without cached Markdown/chunks:

```bash
cd backend/rag
../.venv/bin/docling-tools models download layout tableformer --output-dir docling_models
```

The ingestion task uses `docling_models/` by default. Set `DOCLING_ARTIFACTS_PATH` when
the artifacts are stored elsewhere. OCR is disabled for the bundled,
text-based factsheets; scanned PDFs require separately provisioning an OCR
model and enabling OCR in `ingestion/pdf_parser.py`.

Tables are retained intact in Markdown and also expanded into row/column
statements for retrieval. Common SIP performance labels affected by missing
PDF font glyphs are normalized without changing their numeric cells. For an
unambiguous question that specifies both a SIP period and a table metric, the
app reads the matching cell directly and verifies that the cited chunk
contains its value. The table-aware index uses a new Qdrant collection and
rebuilds the next time the factsheet indexing command runs.

Docling prefers the first CUDA GPU visible to the indexing process. Set
`DOCLING_DEVICE=cpu` to force CPU processing or `DOCLING_DEVICE=auto` to use
CUDA when available and otherwise fall back to CPU. CUDA requires an NVIDIA
driver visible inside the indexing environment; the installed PyTorch build
includes CUDA 12.8 support.

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
