import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


User = get_user_model()


class SignUpSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        min_length=8,
        max_length=128,
        write_only=True,
        trim_whitespace=False,
    )
    first_name = serializers.CharField(max_length=150, trim_whitespace=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, trim_whitespace=True)

    def validate_email(self, value):
        email = value.strip().casefold()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_first_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter your name.")
        return value.strip()

    def create(self, validated_data):
        email = validated_data.pop("email")
        password = validated_data.pop("password")
        # The server-generated opaque username is the internal owner key. It is
        # never accepted from the client, unlike the old free-form user_id.
        return User.objects.create_user(
            username=uuid.uuid4().hex,
            email=email,
            password=password,
            **validated_data,
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, trim_whitespace=True, required=False)

    def validate_first_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter your name.")
        return value.strip()
