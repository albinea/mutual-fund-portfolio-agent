from rest_framework import serializers

from .models import RagQuestionJob


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
    retrieved_chunks = serializers.ListField(child=serializers.JSONField(), required=False)
    answer_method = serializers.CharField(required=False)
    usage = serializers.ListField(child=serializers.JSONField(), required=False)
    tool_trace = serializers.ListField(child=serializers.JSONField(), required=False)
    metadata = serializers.JSONField(required=False)
    error_code = serializers.CharField(required=False)


class ConversationMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    metadata = serializers.JSONField(required=False)


class ConversationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    latest_message_preview = serializers.CharField(allow_blank=True)
    message_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ConversationListSerializer(serializers.Serializer):
    results = ConversationSummarySerializer(many=True)


class ConversationDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    messages = ConversationMessageSerializer(many=True)


class RagQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=4000,
    )
    fund_scope = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    top_k = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=10,
    )

    def validate_question(self, value):
        question = value.strip()
        if not question:
            raise serializers.ValidationError("Question cannot be blank.")
        return question

    def validate_fund_scope(self, value):
        return value.strip() or None


class RagSourceSerializer(serializers.Serializer):
    document = serializers.CharField()
    page = serializers.IntegerField(min_value=1)
    labels = serializers.ListField(child=serializers.CharField())


class RagEvidenceChunkSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=True)
    document = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    page = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    score = serializers.FloatField(required=False, allow_null=True)
    fund_name = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    document_type = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    published_date = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    visual_fallback = serializers.BooleanField(required=False)


class RagUsageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("answer", "vision"))
    model = serializers.CharField()
    requests = serializers.IntegerField(min_value=0)
    input_tokens = serializers.IntegerField(min_value=0)
    output_tokens = serializers.IntegerField(min_value=0)
    input_reports = serializers.IntegerField(min_value=0)
    output_reports = serializers.IntegerField(min_value=0)
    estimated_cost = serializers.CharField()


class RagAnswerSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    error_code = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    answer = serializers.CharField(allow_blank=True)
    draft_answer = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    confidence = serializers.FloatField(min_value=0, max_value=1)
    fund_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    answer_method = serializers.ChoiceField(
        choices=(
            "rag_only",
            "rag_table",
            "rag_plus_vlm",
            "rag_vlm_unaccepted",
            "rag_vlm_unavailable",
        )
    )
    visual_fallback_triggered = serializers.BooleanField()
    visual_fallback_used = serializers.BooleanField()
    table_answer_used = serializers.BooleanField()
    grounding_error = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    sources = RagSourceSerializer(many=True)
    retrieved_chunks = RagEvidenceChunkSerializer(many=True)
    usage = RagUsageSerializer(many=True)
    indexed_documents = serializers.ListField(child=serializers.CharField())


class RagJobAcceptedSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=RagQuestionJob.Status.choices)
    poll_url = serializers.CharField()


class RagJobStatusSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=RagQuestionJob.Status.choices)
    poll_url = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    result = RagAnswerSerializer(required=False, allow_null=True)
