# Evaluation Report

**System:** Mutual Fund Portfolio Intelligence Agent<br>
**Report date:** 2 October 2026<br>
**Evaluation artifact:** `backend/rag/evaluation/answer_results.json`

## Executive summary

The fund-document RAG path was evaluated on a controlled 20-question
regression suite covering HDFC Medium to Long Term Fund facts. Every evaluated
answer contained the required fact, cited the expected page, and passed the
runtime grounding check. No answer execution failed.

| Measure | Result |
| --- | ---: |
| Grounded answer accuracy | **100%** (20/20) |
| Retrieval expected-page recall at top 5 | **100%** (20/20) |
| Retrieval latency, p50 / p95 | **8.5 ms / 9.3 ms** |
| Answer execution failure rate | **0%** (0/20) |
| Estimated text-model cost per logical query | **$0.00063** |

## Evaluation design

- **Questions:** 20 curated questions on objective, risk, benchmark, returns,
  SIP values, dates, portfolio holdings, and expense ratio.
- **Corpus:** 13 page-aware chunks from four pages of the August 2026 HDFC
  factsheet. The corpus intentionally includes an HDFC ELSS page as a
  wrong-fund citation distractor.
- **Retrieval:** fund-scoped, top-5 semantic retrieval using
  `intfloat/multilingual-e5-base` and a temporary in-memory Qdrant collection.
- **Answer generation:** `gemma4:31b`; the optional visual fallback was
  disabled so this measures the normal grounded text/table path.
- **Correctness rule:** an answer is counted as correct only when required
  facts are present, the expected source page is cited, a citation is present,
  and runtime grounding passes.

This is a focused regression benchmark, not a claim of equivalent performance
across every fund, document type, or production workload.

## Accuracy

| Metric | Result | Interpretation |
| --- | ---: | --- |
| Answer fact accuracy | 100% (20/20) | All expected facts or patterns were present. |
| Citation page accuracy | 100% (20/20) | Every answer cited its expected factsheet page. |
| Citation completeness | 100% (20/20) | Every answer returned at least one citation. |
| Grounding pass rate | 100% (20/20) | No answer was withheld or marked as an unverified draft. |
| Composite grounded accuracy | 100% (20/20) | Facts, citation, and grounding all passed. |
| Expected evidence-term recall at top 5 | 100% | Retrieved evidence contained every required term. |
| Fund-scope purity at top 5 | 100% | All retrieved chunks matched the requested fund. |
| Citation metadata coverage at top 5 | 100% | All retrieved chunks had document and page metadata. |
| Mean reciprocal rank at top 5 | 0.80 | The expected page ranked near the top on average. |
| Confidence Brier score | 0.0225 | Lower is better; confidence aligned well with benchmark correctness. |
| High-confidence error rate (>=80%) | 0% | No incorrect answer was reported at high confidence. |

## Latency

The evaluator measures retrieval after embedding-model warm-up, excluding
one-time initialization work:

| Percentile | Retrieval latency |
| --- | ---: |
| p50 | 8.5 ms |
| p95 | 9.3 ms |

These numbers measure local in-memory retrieval only. They intentionally do
not represent end-to-end user latency, which also depends on the Ollama model,
network, job-queue wait time, and document size. Production monitoring should
record request-to-completion latency separately.

## Failure rate

All 20 questions completed with an answer; the evaluation recorded **0 answer
execution errors**, for a **0% failure rate**. The evaluator also made 16
answer-model requests across the 20 logical questions; four table-derived
(`rag_table`) answers did not require an answer-model call.

## Cost per query

The run recorded 87,000 input tokens and 953 output tokens across the 20
logical questions. At the current Ollama Cloud `gemma4` published rates of
$0.14 per million input tokens and $0.40 per million output tokens, the
estimated cost is:

```text
Input:   87,000 / 1,000,000 x $0.14 = $0.012180
Output:     953 / 1,000,000 x $0.40 = $0.000381
Total:                              $0.012561

Cost per logical query: $0.012561 / 20 = $0.000628 ~= $0.00063
```

That is approximately **0.063 US cents per evaluated user query**, or
**$0.00079 per answer-model invocation**. This estimate assumes the run's
`gemma4:31b` Cloud configuration is billed at the published `gemma4` rate,
does not include any plan subscription or included credits, and excludes
visual fallback, infrastructure, and any non-model costs. Ollama’s published
model prices may change; see [Ollama pricing](https://registry.ollama.com/pricing).

## Reproduce

From `backend/`, with the configured Ollama credentials in `backend/.env`:

```bash
.venv/bin/python rag/evaluation/evaluate.py --with-answers --output rag/evaluation/answer_results.json
```

For a free, offline retrieval-only pass:

```bash
.venv/bin/python rag/evaluation/evaluate.py
```

The retrieval-only run makes no provider calls and therefore does not produce
answer accuracy, end-to-end failure, or model-cost figures.
