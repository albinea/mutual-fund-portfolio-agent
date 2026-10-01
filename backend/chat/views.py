from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ChatRequestSerializer, ChatResponseSerializer
from .services import run_chat


class ChatView(APIView):
    def post(self, request):
        request_serializer = ChatRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        result = run_chat(**request_serializer.validated_data)

        response_serializer = ChatResponseSerializer(data=result)
        if not response_serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "error_code": "INVALID_AGENT_RESPONSE",
                    "answer": "The agent returned an invalid response.",
                    "sources": [],
                    "tool_trace": [],
                    "metadata": {},
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(response_serializer.validated_data)