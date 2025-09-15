from django.apps import AppConfig

class SapIntegrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sap_integration"

    def ready(self):
        from .sap_service import SAPService
        try:
            SAPService.login()
        except Exception:
            pass  # Don't crash app if SAP is down at startup