from django.urls import path

from .rag_views import RagAnswerView, RagJobCreateView, RagJobStatusView


urlpatterns = [
    path("jobs/", RagJobCreateView.as_view(), name="rag-job-create"),
    path(
        "jobs/<uuid:job_id>/",
        RagJobStatusView.as_view(),
        name="rag-job-status",
    ),
    path("answer/", RagAnswerView.as_view(), name="rag-answer"),
]
