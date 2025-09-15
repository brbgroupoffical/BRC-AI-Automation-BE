from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import uuid
from django.conf import settings

def automation_upload_to(instance, filename):
    # store under media/automations/{uuid4}_{filename}
    return f'automations/{uuid.uuid4().hex}_{filename}'


class GRNAutomation(models.Model):
    """Represents one automation run triggered by a user."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grn_automations"
    )
    file = models.FileField(upload_to=automation_upload_to)  # ✅ must exist here
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Automation {self.pk} for {self.user.username}"


class AutomationStep(models.Model):
    """Represents each step in the automation pipeline."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    automation = models.ForeignKey(GRNAutomation, on_delete=models.CASCADE, related_name="steps")
    step_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ("automation", "step_name")
        ordering = ["id"]

    def __str__(self):
        return f"{self.step_name} - {self.status}"
