from django.db import models


class ProcessedEmail(models.Model):
    message_id = models.CharField(max_length=255, unique=True, db_index=True)
    email_from = models.EmailField()
    email_subject = models.TextField()
    pdf_name = models.CharField(max_length=255)
    case_number = models.IntegerField()
    case_name = models.CharField(max_length=100)
    confidence = models.FloatField()
    api_success = models.BooleanField(default=False)
    api_response = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'email_automation_processed'
        ordering = ['-processed_at']
        
    def __str__(self):
        return f"{self.pdf_name} - Case {self.case_number}"