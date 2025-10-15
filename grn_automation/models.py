from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid

def automation_upload_to(instance, filename):
    return f'automations/{uuid.uuid4().hex}_{filename}'

class GRNAutomation(models.Model):
    """Represents one automation run triggered by a user."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
    
    class CaseType(models.TextChoices):
        ONE_TO_ONE = "one_to_one", "One to One"
        ONE_TO_MANY = "one_to_many", "One to Many"
        MANY_TO_MANY = "many_to_many", "Many to Many"
    
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
    case_type = models.CharField(
        max_length=20, choices=CaseType.choices, null=True
    )
    validation_message = models.TextField(null=True, blank=True)  
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["case_type"]),
        ]
    
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
        GRN_DETAILS = "grn_details", "GRN Details"
        FETCH_VENDOR_CODE = "fetch_vendor_code", "Fetch Vendor Code"
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
    message = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["automation", "step_name"], name="unique_step_per_automation"
            )
        ]
    
    def __str__(self):
        return f"{self.step_name} - {self.status}"


class ValidationResult(models.Model):
    """Stores validation results for each invoice date."""
    class ValidationStatus(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        PARTIAL = "PARTIAL", "Partial"
    
    class PostingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        POSTED = "posted", "Posted"
        FAILED = "failed", "Failed"
    
    automation = models.ForeignKey(
        GRNAutomation, 
        on_delete=models.CASCADE, 
        related_name="validation_results"
    )
    invoice_date = models.DateField()
    validation_status = models.CharField(
        max_length=20, 
        choices=ValidationStatus.choices
    )
    card_code = models.CharField(max_length=100)
    doc_entry = models.IntegerField()
    doc_date = models.DateField()
    bpl_id = models.IntegerField()
    
    # Posting fields
    posting_status = models.CharField(
        max_length=20, 
        choices=PostingStatus.choices, 
        default=PostingStatus.PENDING
    )
    posting_message = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["automation", "invoice_date"]),
            models.Index(fields=["posting_status"]),
        ]
    
    def __str__(self):
        return f"Validation {self.id} - {self.invoice_date} - {self.validation_status}"


class DocumentLine(models.Model):
    """Stores document lines for each validation result."""
    validation_result = models.ForeignKey(
        ValidationResult, 
        on_delete=models.CASCADE, 
        related_name="document_lines"
    )
    line_num = models.IntegerField()
    remaining_open_quantity = models.DecimalField(
        max_digits=15, 
        decimal_places=2
    )
    
    class Meta:
        ordering = ['line_num']
        indexes = [
            models.Index(fields=["validation_result", "line_num"]),
        ]
    
    def __str__(self):
        return f"Line {self.line_num} - Qty: {self.remaining_open_quantity}"