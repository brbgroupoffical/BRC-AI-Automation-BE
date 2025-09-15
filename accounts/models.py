from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    email = models.EmailField(_("email address"), unique=True)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["email"], name="accounts_user_email_idx"),
            models.Index(fields=["username"], name="accounts_user_username_idx"),
        ]