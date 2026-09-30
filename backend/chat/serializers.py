from rest_framework import serializers


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


class ChatResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    answer = serializers.CharField(required=False, allow_blank=True)
    source = serializers.JSONField(required=False, allow_null=True)
    error_code = serializers.CharField(required=False)
