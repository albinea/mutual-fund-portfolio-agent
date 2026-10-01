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
