from django.apps import AppConfig
import threading
import os


class EmailAutomationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'email_automation'
    
    webhook_thread = None
    should_stop = False

    def ready(self):
        """Start webhook when Django starts (only in main process)"""
        # Only run in the main process (not in reloader or migrations)
        if os.environ.get('RUN_MAIN') == 'true':
            from .services.email_trigger import start_webhook_server
            
            print("\n" + "="*60)
            print("EMAIL AUTOMATION - Starting webhook server...")
            print("="*60)
            
            # Start webhook in background thread
            self.webhook_thread = threading.Thread(
                target=start_webhook_server,
                daemon=True
            )
            self.webhook_thread.start()
            
            print("[EMAIL AUTOMATION] Webhook server started ✓")
            print("="*60 + "\n")