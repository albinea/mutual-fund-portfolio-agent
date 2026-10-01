from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ChatRequestSerializer
from .services import run_chat

from drf_spectacular.utils import OpenApiResponse, extend_schema

from .serializers import ChatRequestSerializer, ChatResponseSerializer

@extend_schema(
    tags=["Chat"],
    request=ChatRequestSerializer,
    responses={
        200: ChatResponseSerializer,
        400: OpenApiResponse(description="Invalid request body."),
        503: OpenApiResponse(
            description="Agent or Ollama service is unavailable."
        ),
    },
    description=(
        "Sends a user question to the agent. "
        "The agent may call portfolio tools or RAG/document-search tools."
    ),
)

class ChatView(APIView):
    """Expose the existing portfolio agent through the Django REST API."""

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        result = run_chat(
            message=payload["message"],
            user_id=payload["user_id"],
            conversation_context=payload["conversation_context"],
        )
        response_status = status.HTTP_200_OK if result.get("success") else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(result, status=response_status)
