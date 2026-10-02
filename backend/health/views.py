from drf_spectacular.utils import OpenApiTypes, extend_schema
from django.db import connections
from django.db.utils import DatabaseError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness/readiness check safe for a reverse proxy or container probe."""

    authentication_classes = []
    permission_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        try:
            connections["default"].ensure_connection()
        except DatabaseError:
            return Response(
                {
                    "status": "unavailable",
                    "service": "mutual-fund-portfolio-agent-api",
                    "database": "unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "status": "ok",
                "service": "mutual-fund-portfolio-agent-api",
                "database": "ok",
            }
        )
