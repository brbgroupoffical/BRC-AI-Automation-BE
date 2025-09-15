from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()

class UsernameOrEmailBackend(ModelBackend):
    """Authenticate with either username or email (case-insensitive for email)."""
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        user = None
        try:
            user = UserModel.objects.get(Q(username=username) | Q(email__iexact=username))
        except UserModel.DoesNotExist:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None