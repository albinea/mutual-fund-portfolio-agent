from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(
    required=False,
    allow_null=True,
    )
    
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
    conversation_context = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
        max_length=20,
    )

    def validate_conversation_context(self, value):
        valid_roles = {"user", "assistant", "model"}
        cleaned = []
        for item in value:
            role = item.get("role")
            content = item.get("content")
            if role not in valid_roles or not isinstance(content, str) or not content.strip():
                raise serializers.ValidationError(
                    "Each context item must have a role and non-empty content."
                )
            cleaned.append({"role": role, "content": content.strip()[:4000]})
        return cleaned


class ChatResponseSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False)

    success = serializers.BooleanField()
    answer = serializers.CharField(required=False, allow_blank=True)
    sources = serializers.ListField(child=serializers.JSONField(), required=False)
    tool_trace = serializers.ListField(child=serializers.JSONField(), required=False)
    metadata = serializers.JSONField(required=False)
    error_code = serializers.CharField(required=False)
