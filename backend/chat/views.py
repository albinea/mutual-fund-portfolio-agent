from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatMessage, Conversation
from .serializers import ChatRequestSerializer, ChatResponseSerializer
from .services import run_chat


@extend_schema(
    tags=["Chat"],
    request=ChatRequestSerializer,
    responses={
        200: ChatResponseSerializer,
        400: OpenApiResponse(description="Invalid request body."),
        404: OpenApiResponse(
            description="Conversation was not found for this user."
        ),
        503: OpenApiResponse(
            description="Agent or Ollama service is unavailable."
        ),
    },
    description=(
        "Sends a user question to the agent and stores conversation "
        "messages in the database. The agent may call portfolio tools "
        "or RAG/document-search tools."
    ),
)
class ChatView(APIView):
    """Send a message to the agent and persist the conversation."""

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        user_id = payload["user_id"]
        conversation_id = payload.get("conversation_id")

        if conversation_id:
            try:
                conversation = Conversation.objects.get(
                    id=conversation_id,
                    user_id=user_id,
                )
            except Conversation.DoesNotExist:
                raise NotFound("Conversation was not found for this user.")
        else:
            conversation = Conversation.objects.create(user_id=user_id)

        recent_messages = list(
            conversation.messages.order_by("-created_at")[:10]
        )
        recent_messages.reverse()

        conversation_context = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in recent_messages
        ]

        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.USER,
            content=payload["message"],
        )

        result = run_chat(
            message=payload["message"],
            user_id=user_id,
            conversation_context=conversation_context,
        )

        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.ASSISTANT,
            content=result.get("answer", ""),
        )

        conversation.save(update_fields=["updated_at"])
        result["conversation_id"] = conversation.id

        response_status = (
            status.HTTP_200_OK
            if result.get("success")
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(result, status=response_status)