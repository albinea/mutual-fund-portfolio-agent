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