from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()

class AuthFlowTests(APITestCase):
    def setUp(self):
        self.email = "jane@example.com"
        self.username = "jane"
        self.password = "StrongPass!234"
        self.user = User.objects.create_user(username=self.username, email=self.email, password=self.password)

    def test_register_login_logout(self):
        # Register
        url = reverse("auth-register")
        res = self.client.post(url, {
            "email": "john@example.com",
            "username": "john",
            "password1": "AStronger!234",
            "password2": "AStronger!234",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Login by username
        url = reverse("auth-login")
        res = self.client.post(url, {"username": self.username, "password": self.password}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        access = res.data["access"]
        refresh = res.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        # Me
        me = self.client.get(reverse("auth-me"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], self.email)

        # Logout
        out = self.client.post(reverse("auth-logout"), {"refresh": refresh}, format="json")
        self.assertEqual(out.status_code, status.HTTP_205_RESET_CONTENT)

    def test_login_with_email(self):
        res = self.client.post(reverse("auth-login"), {"username": self.email, "password": self.password}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)