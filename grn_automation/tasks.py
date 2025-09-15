# from celery import shared_task
# import logging, traceback
# from django.utils import timezone
# from grn_automation.models import GRNAutomation, AutomationStep
# from utils.vendor import get_vendor_code
# from utils.grns import fetch_grns_for_vendor, filter_grn_response
# from utils.matcher import matching_grns
# from utils.validation import validation
# from utils.invoice import create_ap_invoice
# from sap_integration.sap_service import SAPService

# logger = logging.getLogger(__name__)


# def _update_step(automation, step_name, status, error_message=None):
#     """Helper to update AutomationStep status."""
#     step = AutomationStep.objects.get(automation=automation, step_name=step_name)
#     step.status = status
#     step.error_message = error_message
#     step.save()


# @shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
# def run_full_automation(self, automation_id):
#     """
#     Run the full GRN → Invoice automation sequentially.
#     """
#     try:
#         automation = GRNAutomation.objects.get(pk=automation_id)
#         logger.info(f"🚀 Starting automation {automation_id}")

#         # 1. Ensure SAP session
#         _update_step(automation, "sap_login", AutomationStep.Status.PENDING)
#         SAPService.ensure_session()
#         _update_step(automation, "sap_login", AutomationStep.Status.SUCCESS)

#         # 2. Extract vendor code from GRN
#         _update_step(automation, "extraction", AutomationStep.Status.PENDING)
#         vendor_code, grn_po, pdf_data = get_vendor_code(automation.file.path)
#         if not vendor_code or vendor_code == "Not Found":
#             raise RuntimeError("Vendor code not found")
#         _update_step(automation, "extraction", AutomationStep.Status.SUCCESS)

#         # 3. Fetch GRNs
#         _update_step(automation, "fetch_open_grn", AutomationStep.Status.PENDING)
#         grns = fetch_grns_for_vendor(vendor_code)
#         filtered_grns = [filter_grn_response(g) for g in grns]
#         if not filtered_grns:
#             raise RuntimeError("No GRNs found for vendor")
#         _update_step(automation, "fetch_open_grn", AutomationStep.Status.SUCCESS)

#         # 4. Match GRN
#         _update_step(automation, "filter_grn", AutomationStep.Status.PENDING)
#         result = matching_grns(vendor_code, grn_po, filtered_grns)
#         if not result or not result.get("matched_payload"):
#             raise RuntimeError("No matching GRN found for PO")
#         matched_payload = result["matched_payload"]
#         _update_step(automation, "filter_grn", AutomationStep.Status.SUCCESS)

#         # 5. Validate Invoice
#         _update_step(automation, "validation", AutomationStep.Status.PENDING)
#         validation_result = validation(automation.file.path, matched_payload)
#         if validation_result["status"] != "VALIDATION PASSED":
#             raise RuntimeError(f"Validation failed: {validation_result.get('details')}")
#         _update_step(automation, "validation", AutomationStep.Status.SUCCESS)

#         # 6. Create AP Invoice
#         _update_step(automation, "booked", AutomationStep.Status.PENDING)
#         invoice_result = create_ap_invoice(validation_result)
#         if invoice_result.get("status") != "Created":
#             raise RuntimeError(f"Invoice creation failed: {invoice_result}")
#         _update_step(automation, "booked", AutomationStep.Status.SUCCESS)

#         # ✅ Done
#         automation.completed_at = timezone.now()
#         automation.save()
#         logger.info(f"✅ Automation {automation_id} completed")

#     except Exception as e:
#         logger.error(f"❌ Automation {automation_id} failed: {e}")
#         traceback.print_exc()
#         # Mark failed step
#         AutomationStep.objects.filter(
#             automation=automation, status=AutomationStep.Status.PENDING
#         ).update(status=AutomationStep.Status.FAILED, error_message=str(e))
#         raise
