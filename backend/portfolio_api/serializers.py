from rest_framework import serializers


class FundComparisonRequestSerializer(serializers.Serializer):
    fund_ids = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=2,
        max_length=5,
    )


class SipRequestSerializer(serializers.Serializer):
    monthly_investment = serializers.FloatField(min_value=0)
    duration_years = serializers.IntegerField(min_value=1, max_value=50)
    expected_annual_return = serializers.FloatField(min_value=-99, max_value=100)


class ExpectedWealthRequestSerializer(serializers.Serializer):
    initial_investment = serializers.FloatField(min_value=0)
    additional_investment = serializers.FloatField(min_value=0)
    frequency = serializers.ChoiceField(choices=["monthly", "yearly"])
    duration_years = serializers.IntegerField(min_value=1, max_value=50)
    expected_annual_return = serializers.FloatField(min_value=-99, max_value=100)


class WatchlistCreateSerializer(serializers.Serializer):
    user_id = serializers.CharField(max_length=255)
    symbol = serializers.CharField(max_length=40)


class ApiEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.JSONField(required=False)
    sources = serializers.ListField(child=serializers.JSONField(), required=False)
    message = serializers.CharField(required=False, allow_null=True)
    error_code = serializers.CharField(required=False)
