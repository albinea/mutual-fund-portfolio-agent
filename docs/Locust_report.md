# Load-Test Report

**Project:** Mutual Fund Portfolio Intelligence Agent  
**Test date:** 3 October 2026  
**Environment:** Local Docker-backed deployment (Django API, MySQL, Qdrant, and RAG worker)

## Purpose

Validate two different behaviours:

1. The Django API remains responsive under lightweight concurrent traffic and enforces rate limits.
2. The asynchronous RAG workflow processes concurrent document-research requests with grounded, cited answers.

## 1. Locust API-rate-limit test

### Scenario

- Peak concurrent users: **5**
- User spawn rate: **1 user/second**
- Target: lightweight Django health endpoint
- Observed request rate: approximately **3.2–3.5 requests/second**

### Observations

| Metric | Result |
|---|---:|
| Peak simulated users | 5 |
| Sustained request rate | ~3.2–3.5 RPS |
| Typical p50 latency | ~2 ms |
| Typical p95 latency | ~20–24 ms |
| Rate-limit response | HTTP 429 under sustained anonymous traffic |

### Interpretation

The HTTP **429 Too Many Requests** responses were expected. The application applies an anonymous-request throttle of **60 requests per minute**. A sustained rate above roughly one request per second crosses that threshold, so Django rejects excess requests quickly instead of allowing uncontrolled traffic to consume database or AI resources.

This confirms that rate limiting is active and protects the API. The low latency of rejected requests is expected because the request is blocked before expensive application work is performed.

## 2. End-to-end RAG concurrency test

The RAG workflow was tested separately through the application's authenticated asynchronous job API. This measures the complete path: job submission, retrieval, answer generation, grounding validation, citations, and result polling.

| Concurrent users | Jobs completed | Completion rate | Grounded-answer rate | Submission p95 | End-to-end p50 | End-to-end p95 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 / 1 | 100% | 100% | 67.02 ms | 2.53 s | 2.53 s |
| 2 | 2 / 2 | 100% | 100% | 70.10 ms | 2.55 s | 4.58 s |
| 5 | 5 / 5 | 100% | 100% | 117.23 ms | 6.87 s | 10.92 s |

### RAG result details

- **Failed jobs:** 0
- **Timed-out jobs:** 0
- **Client or API errors:** 0
- **Answers with sources:** 100%
- **Answer method:** `rag_only` for every tested job
- **Visual/VLM fallback:** not required during these tests
- **Confidence:** 0.85 for each successful tested answer

## Conclusion

The platform demonstrated two important production-readiness behaviours:

- It protects public API endpoints through enforced request throttling under sustained traffic.
- It reliably processes concurrent RAG research jobs asynchronously, returning grounded answers with citations for every tested request.

At five concurrent RAG users, all requests completed successfully. Longer end-to-end times are expected because document retrieval and model-backed answer generation are processed by the background worker, while the API returns job submission acknowledgements quickly and keeps the user interface responsive.
