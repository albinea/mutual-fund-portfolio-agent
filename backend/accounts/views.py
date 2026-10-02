from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, ProfileUpdateSerializer, SignUpSerializer


User = get_user_model()


def _account_data(user) -> dict[str, str | bool]:
    return {
        "user_id": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
    }


def _success(
    data: dict,
    message: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    return Response({"success": True, "data": data, "message": message}, status=status_code)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfCookieView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return _success({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class SignUpView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return _success(
            _account_data(user),
            "Your account is ready.",
            status.HTTP_201_CREATED,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().casefold()
        user_record = User.objects.filter(email__iexact=email, is_active=True).first()
        user = authenticate(
            request,
            username=user_record.get_username() if user_record else email,
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {
                    "success": False,
                    "error_code": "INVALID_CREDENTIALS",
                    "message": "Email or password is incorrect.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return _success(_account_data(user), "Signed in successfully.")


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return _success({}, "You have signed out.")


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success(_account_data(request.user))

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(request.user, field, value)
        if serializer.validated_data:
            request.user.save(update_fields=[*serializer.validated_data.keys()])
        return _success(_account_data(request.user), "Profile updated.")
