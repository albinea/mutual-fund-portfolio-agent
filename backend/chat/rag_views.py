"""Django API endpoint for evidence-backed FundLens questions."""

from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from django.urls import reverse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RagQuestionJob
from .serializers import (
    RagAnswerSerializer,
    RagJobAcceptedSerializer,
    RagJobStatusSerializer,
    RagQuestionSerializer,
)
from .services import run_fundlens_rag


logger = logging.getLogger(__name__)


@extend_schema(
    tags=["RAG"],
    request=RagQuestionSerializer,
    responses={
        202: RagJobAcceptedSerializer,
        400: OpenApiResponse(description="Invalid RAG request."),
    },
    description=(
        "Queues a fund-document question for the RAG worker and returns a job "
        "identifier immediately. Poll the provided URL for the final answer, "
        "citations, retrieved evidence, and usage."
    ),
)
class RagJobCreateView(APIView):
    """Queue a RAG request without holding the HTTP connection during inference."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_serializer = RagQuestionSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        payload = request_serializer.validated_data
        job = RagQuestionJob.objects.create(
            user_id=request.user.get_username(),
            question=payload["question"],
            fund_scope=payload.get("fund_scope"),
            top_k=payload["top_k"],
        )
        poll_url = reverse("rag-job-status", kwargs={"job_id": job.id})
        response_serializer = RagJobAcceptedSerializer(
            data={"job_id": job.id, "status": job.status, "poll_url": poll_url}
        )
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    tags=["RAG"],
    responses={
        200: RagJobStatusSerializer,
        404: OpenApiResponse(description="RAG job was not found."),
    },
    description=(
        "Returns queued/running status, or the completed result containing the "
        "answer, citations, retrieved chunks for the evidence panel, and usage."
    ),
)
class RagJobStatusView(APIView):
    """Return progress or the complete evidence-backed result for a queued job."""

    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        job = get_object_or_404(
            RagQuestionJob,
            id=job_id,
            user_id=request.user.get_username(),
        )
        data = {
            "job_id": job.id,
            "status": job.status,
            "poll_url": reverse("rag-job-status", kwargs={"job_id": job.id}),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        if job.status in (RagQuestionJob.Status.COMPLETED, RagQuestionJob.Status.FAILED):
            data["result"] = job.result

        response_serializer = RagJobStatusSerializer(data=data)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)


@extend_schema(
    tags=["RAG"],
    request=RagQuestionSerializer,
    responses={
        200: RagAnswerSerializer,
        400: OpenApiResponse(description="Invalid RAG request."),
        503: OpenApiResponse(description="RAG service is unavailable."),
    },
    description=(
        "Answers a mutual-fund document question and returns verified sources, "
        "retrieved evidence chunks, answer method, and model usage. Expected "
        "evidence gaps are returned as a normal 200 response."
    ),
)
class RagAnswerView(APIView):
    """Run fund-scoped RAG without changing the existing portfolio chat API."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_serializer = RagQuestionSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        payload = request_serializer.validated_data
        from fundlens_rag.app.usage import UsageTracker

        usage_tracker = UsageTracker()

        try:
            result = run_fundlens_rag(
                question=payload["question"],
                fund_scope=payload.get("fund_scope"),
                top_k=payload["top_k"],
                usage_tracker=usage_tracker,
            )
            result = _add_usage_cost_labels(result)
        except Exception:
            logger.exception("FundLens RAG endpoint failed")
            result = _unavailable_result(usage_tracker.snapshot())
            if result["usage"]:
                result = _add_usage_cost_labels(result)
            response_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            # A valid question that has no match or insufficient evidence is
            # still a successfully processed request, not a server outage.
            response_status = status.HTTP_200_OK

        response_serializer = RagAnswerSerializer(data=result)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=response_status)


def _add_usage_cost_labels(result: dict) -> dict:
    """Attach configured cost/status labels without exposing server secrets."""
    from fundlens_rag.app.usage import UsageTracker

    records = result.get("usage", [])
    rows = UsageTracker.display_rows(records)
    result["usage"] = [
        {
            **record,
            "estimated_cost": row["Estimated cost (USD)"],
        }
        for record, row in zip(records, rows, strict=True)
    ]
    return result


def _unavailable_result(usage: list[dict] | None = None) -> dict:
    return {
        "success": False,
        "error_code": "rag_unavailable",
        "answer": "The document research service is temporarily unavailable.",
        "draft_answer": None,
        "confidence": 0.0,
        "fund_name": None,
        "answer_method": "rag_only",
        "visual_fallback_triggered": False,
        "visual_fallback_used": False,
        "table_answer_used": False,
        "grounding_error": None,
        "sources": [],
        "retrieved_chunks": [],
        "usage": usage or [],
        "indexed_documents": [],
    }
