from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid


def automation_upload_to(instance, filename):
    # store under media/automations/{uuid4}_{filename}
    return f'automations/{uuid.uuid4().hex}_{filename}'


class GRNAutomation(models.Model):
    """Represents one automation run triggered by a user."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grn_automations"
    )
    file = models.FileField(upload_to=automation_upload_to)
    original_filename = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
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

    class Step(models.TextChoices):
        UPLOAD = "upload", "Upload"
        SAP_LOGIN = "sap_login", "SAP Login"
        EXTRACTION = "extraction", "Extraction"
        FETCH_OPEN_GRN = "fetch_open_grn", "Fetch Open GRN"
        FILTER_GRN = "filter_grn", "Filter GRN"
        VALIDATION = "validation", "Validation"
        BOOKED = "booked", "Booked"

    automation = models.ForeignKey(
        GRNAutomation, on_delete=models.CASCADE, related_name="steps"
    )
    step_name = models.CharField(max_length=100, choices=Step.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    message = models.TextField(null=True, blank=True)  # status or error message
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["automation", "step_name"], name="unique_step_per_automation"
            )
        ]
        ordering = ["id"]

    def __str__(self):
        return f"{self.step_name} - {self.status}"

