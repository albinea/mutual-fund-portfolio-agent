"""Database-backed RAG jobs for requests that may outlive an HTTP timeout."""

from __future__ import annotations

import json
import logging
import time

from django.db import transaction
from django.utils import timezone
from rest_framework.renderers import JSONRenderer

from .models import RagQuestionJob
from .rag_views import _add_usage_cost_labels, _unavailable_result
from .serializers import RagAnswerSerializer
from .services import run_fundlens_rag


logger = logging.getLogger(__name__)


def claim_next_rag_job() -> RagQuestionJob | None:
    """Atomically claim one queued job so separate worker processes do not duplicate it."""
    with transaction.atomic():
        job_id = (
            RagQuestionJob.objects.filter(status=RagQuestionJob.Status.QUEUED)
            .order_by("created_at")
            .values_list("id", flat=True)
            .first()
        )
        if job_id is None:
            return None

        claimed = RagQuestionJob.objects.filter(
            id=job_id,
            status=RagQuestionJob.Status.QUEUED,
        ).update(
            status=RagQuestionJob.Status.RUNNING,
            updated_at=timezone.now(),
        )
        if not claimed:
            return None

    return RagQuestionJob.objects.get(id=job_id)


def process_claimed_rag_job(job: RagQuestionJob) -> None:
    """Run RAG once and persist its validated answer, citations, evidence, and usage."""
    from fundlens_rag.app.usage import UsageTracker

    usage_tracker = UsageTracker()
    status_value = RagQuestionJob.Status.COMPLETED

    try:
        result = run_fundlens_rag(
            question=job.question,
            fund_scope=job.fund_scope,
            top_k=job.top_k,
            usage_tracker=usage_tracker,
        )
        result = _add_usage_cost_labels(result)
        answer_serializer = RagAnswerSerializer(data=result)
        answer_serializer.is_valid(raise_exception=True)
        result = json.loads(JSONRenderer().render(answer_serializer.data))
    except Exception:
        logger.exception("FundLens RAG background job failed: %s", job.id)
        status_value = RagQuestionJob.Status.FAILED
        result = _unavailable_result(usage_tracker.snapshot())
        if result["usage"]:
            result = _add_usage_cost_labels(result)
        answer_serializer = RagAnswerSerializer(data=result)
        answer_serializer.is_valid(raise_exception=True)
        result = json.loads(JSONRenderer().render(answer_serializer.data))

    RagQuestionJob.objects.filter(id=job.id).update(
        status=status_value,
        result=result,
        updated_at=timezone.now(),
    )


def run_rag_worker(*, once: bool = False, poll_interval: float = 1.0) -> int:
    """Poll the database and process jobs; intended for a separate process."""
    processed = 0
    while True:
        job = claim_next_rag_job()
        if job is None:
            if once:
                return processed
            time.sleep(max(poll_interval, 0.1))
            continue

        process_claimed_rag_job(job)
        processed += 1
        if once:
            return processed
