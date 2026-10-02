from rest_framework import serializers


class FundComparisonRequestSerializer(serializers.Serializer):
    fund_ids = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=2,
        max_length=5,
    )


class FundSchemeSearchSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=200, trim_whitespace=True)
    limit = serializers.IntegerField(required=False, default=12, min_value=1, max_value=20)


class FundNavComparisonRequestSerializer(serializers.Serializer):
    scheme_codes = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=2,
        max_length=5,
    )
    years = serializers.ChoiceField(choices=[1, 3, 5, 10])

    def validate_scheme_codes(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Select distinct schemes for comparison.")
        return value


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
    symbol = serializers.CharField(max_length=40)


class PortfolioImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField()
    as_of_date = serializers.DateField(required=False)

    def validate_file(self, uploaded_file):
        suffix = uploaded_file.name.rsplit(".", 1)[-1].casefold() if "." in uploaded_file.name else ""
        if suffix not in {"csv", "xlsx"}:
            raise serializers.ValidationError("Upload a CSV or XLSX statement. PDF parsing is not enabled yet.")
        if uploaded_file.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The file must be 2 MB or smaller.")
        return uploaded_file


class FundDisclosureImportRequestSerializer(serializers.Serializer):
    file = serializers.FileField()
    disclosure_date = serializers.DateField(required=False)
    source_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_url = serializers.URLField(required=False, allow_blank=True)

    def validate_file(self, uploaded_file):
        suffix = uploaded_file.name.rsplit(".", 1)[-1].casefold() if "." in uploaded_file.name else ""
        if suffix not in {"csv", "xlsx"}:
            raise serializers.ValidationError("Upload a normalized CSV or XLSX disclosure file. PDF parsing is not enabled.")
        if uploaded_file.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("The file must be 2 MB or smaller.")
        return uploaded_file


class ApiEnvelopeSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = serializers.JSONField(required=False)
    sources = serializers.ListField(child=serializers.JSONField(), required=False)
    message = serializers.CharField(required=False, allow_null=True)
    error_code = serializers.CharField(required=False)
