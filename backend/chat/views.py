from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChatMessage, Conversation
from .serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
)
from .services import run_chat


def _conversation_title(messages: list[ChatMessage]) -> str:
    first_user_message = next(
        (message.content for message in messages if message.role == ChatMessage.Role.USER),
        "New conversation",
    )
    normalized = " ".join(first_user_message.split())
    return normalized[:80] + ("…" if len(normalized) > 80 else "")


def _conversation_or_404(conversation_id, user_id: str) -> Conversation:
    try:
        return Conversation.objects.prefetch_related("messages").get(
            id=conversation_id,
            user_id=user_id,
        )
    except Conversation.DoesNotExist:
        raise NotFound("Conversation was not found for this user.")


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

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        # Ownership always comes from Django's authenticated session, never
        # from a user_id the browser could alter.
        user_id = request.user.get_username()
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

        display_metadata = {
            key: result[key]
            for key in (
                "sources",
                "tool_trace",
                "retrieved_chunks",
                "answer_method",
                "usage",
            )
            if key in result
        }
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.ASSISTANT,
            content=result.get("answer", ""),
            metadata=display_metadata,
        )

        conversation.save(update_fields=["updated_at"])
        result["conversation_id"] = conversation.id

        response_status = (
            status.HTTP_200_OK
            if result.get("success")
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(result, status=response_status)


@extend_schema(
    tags=["Chat"],
    responses={200: ConversationListSerializer},
    description="Lists saved conversations for one portfolio user, newest first.",
)
class ConversationListView(APIView):
    """List a user's persisted chat sessions without exposing other users."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="chat-conversation-list")
    def get(self, request):
        user_id = request.user.get_username()

        conversations = Conversation.objects.filter(user_id=user_id).prefetch_related(
            "messages"
        )
        results = []
        for conversation in conversations:
            messages = list(conversation.messages.all())
            latest_content = messages[-1].content if messages else ""
            results.append(
                {
                    "id": conversation.id,
                    "title": _conversation_title(messages),
                    "latest_message_preview": latest_content[:140],
                    "message_count": len(messages),
                    "created_at": conversation.created_at,
                    "updated_at": conversation.updated_at,
                }
            )

        return Response({"results": results})


@extend_schema(
    tags=["Chat"],
    responses={
        200: ConversationDetailSerializer,
        404: OpenApiResponse(description="Conversation was not found for this user."),
    },
    description="Loads the saved messages for one conversation owned by the user.",
)
class ConversationDetailView(APIView):
    """Return a persisted conversation for the assistant history panel."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="chat-conversation-detail")
    def get(self, request, conversation_id):
        conversation = _conversation_or_404(
            conversation_id,
            request.user.get_username(),
        )

        return Response(
            {
                "id": conversation.id,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
                "messages": [
                    {
                        "role": message.role,
                        "content": message.content,
                        "created_at": message.created_at,
                        "metadata": message.metadata,
                    }
                    for message in conversation.messages.all()
                ],
            }
        )
