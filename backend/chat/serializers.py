from rest_framework import serializers


class ConversationMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant", "model"])
    content = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=4000,
    )


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=4000,
    )
    user_id = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
    )
    conversation_context = ConversationMessageSerializer(
        many=True,
        required=False,
        default=list,
        max_length=20,
    )


class ChatResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    answer = serializers.CharField(required=False, allow_blank=True)
    sources = serializers.ListField(required=False, default=list)
    tool_trace = serializers.ListField(required=False, default=list)
    metadata = serializers.DictField(required=False, default=dict)
    error_code = serializers.CharField(required=False)