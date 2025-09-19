# tasks.py

from celery import shared_task
from django.utils import timezone
from .models import GRNAutomation, AutomationStep
from .utils.extraction import AWSTextractSAPExtractor
from .utils.vendor import get_vendor_code_from_api
from .utils.grns import fetch_grns_for_vendor, filter_grn_response
from .utils.matcher import matching_grns
from .utils.invoice import create_invoice
from .utils.validation import validate_invoice_with_grn
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_grn_automation(automation_id):
    try:
        automation = GRNAutomation.objects.get(id=automation_id)
        step = automation.steps.first()
        file_path = automation.file.path

        # Update automation status to running
        automation.status = GRNAutomation.Status.RUNNING
        automation.save(update_fields=["status"])

        # ---------- Extraction ----------
        extractor = AWSTextractSAPExtractor()
        response = extractor.extract_sap_data(file_path)
        result_status = response["status"]
        message = response["message"]
        result = response["data"]

        step.step_name = AutomationStep.Step.EXTRACTION
        step.status = AutomationStep.Status.SUCCESS if result_status == "success" else AutomationStep.Status.FAILED
        step.message = message
        step.save()

        if result_status != "success" or not result:
            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])
            return

        vendor_name = result["sap_specific_fields"].get("vendor_name")
        grn_po_number = result["sap_specific_fields"].get("po_number")
        vendor_code = result["sap_specific_fields"].get("vendor_code")

        if not vendor_code:
            vendor_code_resp = get_vendor_code_from_api(vendor_name)

            step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
            if vendor_code_resp["status"] != "success":
                step.status = AutomationStep.Status.FAILED
                step.message = vendor_code_resp["message"]
                step.save()

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return

            vendor_code = vendor_code_resp["data"]

        # ---------- Fetch GRNs ----------
        fetch_resp = fetch_grns_for_vendor(vendor_code)
        step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
        step.status = AutomationStep.Status.SUCCESS if fetch_resp["status"] == "success" else AutomationStep.Status.FAILED
        step.message = fetch_resp["message"]
        step.save()

        if fetch_resp["status"] != "success" or not fetch_resp["data"]:
            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])
            return

        all_open_grns = fetch_resp["data"]

        # ---------- Filter + Matching ----------
        try:
            filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
            matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)

            step.step_name = AutomationStep.Step.VALIDATION
            step.status = AutomationStep.Status.SUCCESS
            step.message = f"Matching succeed: Found {len(matched_grns)} matching GRNs."
            step.save()

        except Exception as e:
            step.step_name = AutomationStep.Step.VALIDATION
            step.status = AutomationStep.Status.FAILED
            step.message = f"Matching failed: {str(e)}"
            step.save()

            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])
            return

        # ---------- Validation ----------
        validation_resp = validate_invoice_with_grn(result, matched_grns)
        step.step_name = AutomationStep.Step.VALIDATION
        step.status = AutomationStep.Status.SUCCESS if validation_resp["status"] == "SUCCESS" else AutomationStep.Status.FAILED
        step.message = validation_resp["reasoning"]
        step.save()

        if validation_resp["status"] != "SUCCESS":
            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])
            return

        validated_grns = validation_resp["payload"]

        # ---------- Create Invoice ----------
        invoice_resp = create_invoice(validated_grns)
        step.step_name = AutomationStep.Step.BOOKED
        step.status = AutomationStep.Status.SUCCESS if invoice_resp["status"] == "success" else AutomationStep.Status.FAILED
        step.message = invoice_resp["message"]
        step.save()

        if invoice_resp["status"] != "success":
            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])
            return

        # ---------- Mark Completed ----------
        automation.status = GRNAutomation.Status.COMPLETED
        automation.completed_at = timezone.now()
        automation.save(update_fields=["status", "completed_at"])

    except GRNAutomation.DoesNotExist:
        logger.error(f"Automation with ID {automation_id} not found.")

    except Exception as e:
        logger.exception(f"Error processing automation {automation_id}: {e}")
        automation = GRNAutomation.objects.filter(id=automation_id).first()
        if automation:
            automation.status = GRNAutomation.Status.FAILED
            automation.save(update_fields=["status"])



# celery -A <your_project_name> worker -l info

# # settings.py
# CELERY_BROKER_URL = 'redis://localhost:6379/0'
# CELERY_ACCEPT_CONTENT = ['json']
# CELERY_TASK_SERIALIZER = 'json'
