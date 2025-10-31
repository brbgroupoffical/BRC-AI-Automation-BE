from django.contrib import admin
from .models import ProcessedEmail


@admin.register(ProcessedEmail)
class ProcessedEmailAdmin(admin.ModelAdmin):
    list_display = ('pdf_name', 'case_number', 'case_name', 'confidence', 'api_success', 'processed_at')
    list_filter = ('case_number', 'api_success', 'processed_at')
    search_fields = ('pdf_name', 'email_from', 'email_subject')
    readonly_fields = ('message_id', 'processed_at')
    
    def has_add_permission(self, request):
        return False  # Read-only