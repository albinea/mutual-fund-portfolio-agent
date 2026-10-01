from django.shortcuts import render

# Create your views here.

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({
            "status": "ok",
            "service": "mutual-fund-portfolio-agent-api",
        })
