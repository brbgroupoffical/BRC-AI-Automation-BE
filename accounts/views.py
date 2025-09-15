from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils.translation import gettext_lazy as _

from .serializers import RegisterSerializer, UserSerializer, LoginSerializer

class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

class RefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Blacklist the provided refresh token (supports rotation)."""
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": _("'refresh' token is required.")}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": _("Invalid or expired refresh token.")}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": _("Successfully logged out.")}, status=status.HTTP_205_RESET_CONTENT)

class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user