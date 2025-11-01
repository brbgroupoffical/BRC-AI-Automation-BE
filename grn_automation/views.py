import os
import logging
import requests
from rest_framework import status
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import GRNAutomation, AutomationStep, ValidationResult
from .serializers import AutomationUploadSerializer, GRNAutomationSerializer, VendorCodeSerializer, GRNMatchRequestSerializer, TotalStatsSerializer, CaseTypeStatsSerializer, ValidationResultSerializer, ValidationResultListSerializer, ValidationResultUpdateSerializer
from rest_framework.generics import RetrieveAPIView, ListAPIView
from .utils.vendor import get_vendor_code_from_api
from .utils.grns import fetch_grns_for_vendor, filter_grn_response
from .utils.matcher import matching_grns
from .utils.invoice import create_invoice
from rest_framework.permissions import IsAuthenticated, AllowAny
from .pagination import TenResultsSetPagination
from sap_integration.sap_service import SAPService 
from .services import get_total_stats, get_case_type_stats
from .utils.extraction_and_validation import InvoiceProcessor
from .utils.purchase import fetch_purchase_invoice_by_docnum
from grn_automation.utils.ap_invoice.save_ap_invoices import save_validation_results
from django.shortcuts import get_object_or_404


logger = logging.getLogger(__name__)


SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


class UserAutomationDetailView(RetrieveAPIView):
    """
    Retrieve details of a single automation job.
    - Normal users: can only see their own.
    - Admins: can see all.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:  
            return GRNAutomation.objects.all()
        return GRNAutomation.objects.filter(user=self.request.user)


class UserAutomationListView(ListAPIView):
    """
    List automation jobs with pagination (10 per page).
    - Normal users: see their own jobs.
    - Admins: see all jobs.
    Always sorted by `created_at` in descending order.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TenResultsSetPagination

    def get_queryset(self):
        qs = GRNAutomation.objects.all() if self.request.user.is_staff else GRNAutomation.objects.filter(user=self.request.user)
        return qs.order_by("-created_at")
    

class BaseAutomationUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def create_step(self, automation, step_name, status, message=""):
        """Helper method to create a new automation step."""
        return AutomationStep.objects.create(
            automation=automation,
            step_name=step_name,
            status=status,
            message=message
        )
    
    def update_posting_status(self, automation_id, invoice_date, posting_status, posting_message, validation_result_id=None):
        """
        Helper method to update posting status for a specific validation result.
        
        Args:
            automation_id: ID of the automation
            invoice_date: Date of the invoice to identify the validation result
            posting_status: New posting status (pending/posted/failed)
            posting_message: Message to store
            validation_result_id: Optional ID to directly target specific validation result
        """
        try:
            from datetime import datetime
            
            # Convert invoice_date string to date object if needed
            if isinstance(invoice_date, str):
                invoice_date_obj = datetime.strptime(invoice_date, '%Y-%m-%d').date()
            else:
                invoice_date_obj = invoice_date
            
            # If validation_result_id is provided, use it directly (most reliable)
            if validation_result_id:
                validation_result = ValidationResult.objects.filter(
                    id=validation_result_id,
                    automation_id=automation_id
                ).first()
            else:
                # Fallback: Find by invoice_date and posting_status='pending'
                # This ensures we update unprocessed records
                validation_result = ValidationResult.objects.filter(
                    automation_id=automation_id,
                    invoice_date=invoice_date_obj,
                    posting_status=ValidationResult.PostingStatus.PENDING
                ).first()
            
            if validation_result:
                validation_result.posting_status = posting_status
                validation_result.posting_message = posting_message
                validation_result.save(update_fields=['posting_status', 'posting_message', 'updated_at'])
                logger.info(
                    f"✅ Updated posting status for validation {validation_result.id}: "
                    f"{posting_status} - {posting_message}"
                )
                return True
            else:
                logger.warning(
                    f"⚠️ No ValidationResult found for automation {automation_id}, "
                    f"invoice_date {invoice_date_obj}, validation_result_id {validation_result_id}"
                )
                return False
                
        except Exception as e:
            logger.error(f"❌ Error updating posting status: {str(e)}", exc_info=True)
            return False

    def post(self, request, *args, **kwargs):
        if isinstance(request.data, dict):
            data = request.data
        else:
            data = request.data.dict()
        print(self.case_type)

        serializer = AutomationUploadSerializer(
            data=data,
            context={
                "request": request,
                "case_type": self.case_type 
            }
        )

        if serializer.is_valid():
            automation = serializer.save() 
            automation.file.close()

            # Mark automation as running
            automation.status = GRNAutomation.Status.RUNNING
            automation.save(update_fields=["status"])

            # ---------- SAP Login / VPN Check ----------
            try:
                SAPService.login()
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.SAP_LOGIN,
                    status=AutomationStep.Status.SUCCESS,
                    message="SAP/VPN connection successful. Logged in to SAP."
                )
            except requests.exceptions.RequestException as e:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.SAP_LOGIN,
                    status=AutomationStep.Status.FAILED,
                    message=f"SAP/VPN connection failed. {e}"
                )

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])

                return Response(
                    {"success": False, "message": "SAP/VPN connection failed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.SAP_LOGIN,
                    status=AutomationStep.Status.FAILED,
                    message="SAP login error."
                )

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])

                return Response(
                    {"success": False, "message": "SAP login error."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            file_path = automation.file.path
            openai_api_key = os.getenv("OPENAI_API_KEY")
            extractor = InvoiceProcessor(api_key=openai_api_key)

            # ---------- Extract Markdown ----------
            markdown_resp = extractor.extract_complete_markdown(file_path)
            if markdown_resp["status"] != "success" or not markdown_resp["data"]:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.EXTRACTION,
                    status=AutomationStep.Status.FAILED,
                    message=f"Markdown extraction failed: {markdown_resp['message']}"
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": f"Markdown extraction failed: {markdown_resp['message']}"
                }, status=status.HTTP_400_BAD_REQUEST)

            markdown_text = markdown_resp["data"]
            print("Markdown")
            print(markdown_text)

            # ---------- Extract Vendor Fields ----------
            field_resp = extractor.extract_vendor_fields(markdown_text)
            if field_resp["status"] != "success" or not field_resp["data"]:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.EXTRACTION,
                    status=AutomationStep.Status.FAILED,
                    message=f"Vendor field extraction failed: {field_resp['message']}"
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": f"Vendor field extraction failed: {field_resp['message']}"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            print("Vendor Details")
            print(field_resp)

            vendor_info = field_resp["data"]["vendor_info"]
            vendor_name = vendor_info.get("vendor_name", None)
            grn_po_number = [int(i) for i in vendor_info.get("grn_po_number", [])]
            vendor_code = vendor_info.get("vendor_code", None)
            invoices = field_resp["data"]["invoices"]
            scenario = field_resp["data"]["scenario_detected"]

            print(f"Vendor Name: {vendor_name}, Vendor Code: {vendor_code}, PO Number: {grn_po_number}")

            # ---------- Extraction Step SUCCESS ----------
            self.create_step(
                automation=automation,
                step_name=AutomationStep.Step.EXTRACTION,
                status=AutomationStep.Status.SUCCESS,
                message="Extraction succeeded via OpenAI"
            )

            if not any([vendor_name, grn_po_number, vendor_code]):
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.GRN_DETAILS,
                    status=AutomationStep.Status.FAILED,
                    message="No vendor name or grn po number or vendor code found."
                )

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": "Extraction failed: Required fields (vendor_name, vendor_code, po_number) missing"
                }, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Fetch Vendor Code ----------
            if not vendor_code:
                vendor_code_resp = get_vendor_code_from_api(vendor_name)
                print(f"Vendor Code Response: {vendor_code_resp}")

                if vendor_code_resp["status"] != "success" or not vendor_code_resp.get("data"):
                    self.create_step(
                        automation=automation,
                        step_name=AutomationStep.Step.FETCH_VENDOR_CODE,
                        status=AutomationStep.Status.FAILED,
                        message=vendor_code_resp.get("message", "Vendor code fetch failed")
                    )

                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])

                    return Response({
                        "success": False,
                        "message": f"Vendor code fetch failed: {vendor_code_resp.get('message', 'No vendor code returned')}"
                    }, status=status.HTTP_400_BAD_REQUEST)

                vendor_code = vendor_code_resp["data"]
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.FETCH_VENDOR_CODE,
                    status=AutomationStep.Status.SUCCESS,
                    message=f"Vendor code fetched: {vendor_code}"
                )

            # ---------- Fetch GRNs ----------
            fetch_resp = fetch_grns_for_vendor(vendor_code)

            if fetch_resp["status"] != "success":
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.FETCH_OPEN_GRN,
                    status=AutomationStep.Status.FAILED,
                    message=fetch_resp.get("message", "Failed to fetch GRNs")
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": False, "message": fetch_resp.get("message", "Failed to fetch GRNs")},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if GRNs are already posted
            if fetch_resp.get("already_posted", False):
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.FETCH_OPEN_GRN,
                    status=AutomationStep.Status.SUCCESS,
                    message="GRN already posted."
                )
                
                automation.status = GRNAutomation.Status.COMPLETED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": True, "message": "GRN already posted."},
                    status=status.HTTP_200_OK
                )

            all_open_grns = fetch_resp["data"]
            self.create_step(
                automation=automation,
                step_name=AutomationStep.Step.FETCH_OPEN_GRN,
                status=AutomationStep.Status.SUCCESS,
                message=f"Found {len(all_open_grns)} open GRNs"
            )

            print("Open GRNs")
            print(all_open_grns)

            # ---------- Filter + Matching ----------
            try:
                filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
                print("Filter")
                print(filtered_grns)
                
                if not filtered_grns:
                    self.create_step(
                        automation=automation,
                        step_name=AutomationStep.Step.FILTER_GRN,
                        status=AutomationStep.Status.FAILED,
                        message="No GRNs available after filtering"
                    )
                    
                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])
                    return Response({
                        "success": False,
                        "message": "No GRNs available after filtering"
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.FILTER_GRN,
                    status=AutomationStep.Status.SUCCESS,
                    message=f"Filtered {len(filtered_grns)} GRNs"
                )

                matched_grns_resp = matching_grns(vendor_code, grn_po_number, filtered_grns)
                print("Matching")
                print(matched_grns_resp)

                if not matched_grns_resp or matched_grns_resp.get("status") != "success" or not matched_grns_resp.get("data"):
                    self.create_step(
                        automation=automation,
                        step_name=AutomationStep.Step.VALIDATION,
                        status=AutomationStep.Status.FAILED,
                        message=matched_grns_resp.get("message", "No matching GRNs found after filtering")
                    )
                    
                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])
                    return Response({
                        "success": False,
                        "message": matched_grns_resp.get("message", "No matching GRNs found")
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                matched_grns = matched_grns_resp["data"]

            except Exception as e:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.FILTER_GRN,
                    status=AutomationStep.Status.FAILED,
                    message=f"Filtering/Matching failed: {str(e)}"
                )

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": f"Matching failed: {str(e)}"
                }, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Validation ----------
            validation_resp = extractor.validate_invoice(markdown_text, matched_grns, invoices, scenario)
            print("Validation")
            print(validation_resp)

            if not validation_resp or validation_resp.get("status") != "success" or not validation_resp.get("data"):
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.VALIDATION,
                    status=AutomationStep.Status.FAILED,
                    message=validation_resp.get("message", "Validation failed")
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": False, "message": f"Validation failed: {validation_resp.get('message', 'No validation data returned')}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            validation_results = validation_resp.get("data", {}).get("validation_results", [])
            if not validation_results:
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.VALIDATION,
                    status=AutomationStep.Status.FAILED,
                    message="No validation results returned"
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": False, "message": "No validation results found"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            failed_validations = [r for r in validation_results if r.get("status") != "SUCCESS"]
            if failed_validations:
                failed_reasons = "; ".join([
                    f"Invoice {r.get('invoice_date', 'unknown')}: {r.get('reasoning', 'No reason')}"
                    for r in failed_validations
                ])
                
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.VALIDATION,
                    status=AutomationStep.Status.FAILED,
                    message=failed_reasons
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": False, "message": f"Validation failed: {failed_reasons}"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            self.create_step(
                automation=automation,
                step_name=AutomationStep.Step.VALIDATION,
                status=AutomationStep.Status.SUCCESS,
                message=f"Validated {len(validation_results)} invoice(s) successfully"
            )

            # ========== SAVE VALIDATION RESULTS TO DATABASE ==========
            try:
                save_result = save_validation_results(automation.id, validation_resp)
                
                if save_result['success']:
                    logger.info(f"✅ Validation results saved successfully for automation {automation.id}")
                    logger.info(f"📊 Summary: {save_result['summary']}")
                    
                    # ✅ Extract validation_result_ids from summary dict
                    validation_result_ids = save_result.get('summary', {}).get('validation_result_ids', [])
                    
                    if not validation_result_ids:
                        logger.warning("⚠️ No validation_result_ids returned from save_validation_results")
                else:
                    logger.error(f"❌ Failed to save validation results: {save_result.get('error')}")
                    validation_result_ids = []
                    
            except Exception as e:
                logger.error(f"❌ Error saving validation results: {str(e)}", exc_info=True)
                validation_result_ids = []
            # ========== END: SAVE VALIDATION RESULTS ==========

            validated_grns = [result.get("payload") for result in validation_results]

            # ---------- Create Invoice(s) ----------
            invoice_creation_results = []
            all_invoices_created = True
            invoice_errors = []

            try:
                if len(validation_results) == 1:
                    # CASE 1 (1:1) or CASE 3 (many:1) - Single invoice
                    validation_result = validation_results[0]
                    validated_payload = validation_result.get("payload")
                    invoice_date = validation_result.get("invoice_date")
                    
                    # ✅ Get the corresponding validation_result_id
                    validation_result_id = validation_result_ids[0] if len(validation_result_ids) > 0 else None
                    
                    print(f"Creating invoice for date: {invoice_date}")
                    print(f"Validation Result ID: {validation_result_id}")
                    print(f"Payload: {validated_payload}")
                    
                    invoice_resp = create_invoice(validated_payload, use_dummy=True)
                    print("Invoice Response:")
                    print(invoice_resp)
                    
                    # ========== UPDATE POSTING STATUS ==========
                    if invoice_resp.get("status") == "success":
                        doc_entry = invoice_resp.get("data", {}).get("DocEntry")
                        posting_message = f"Invoice created successfully. DocEntry: {doc_entry}"
                        
                        self.update_posting_status(
                            automation_id=automation.id,
                            invoice_date=invoice_date,
                            posting_status=ValidationResult.PostingStatus.POSTED,
                            posting_message=posting_message,
                            validation_result_id=validation_result_id  # ✅ Pass ID
                        )
                        
                        invoice_creation_results.append({
                            "invoice_date": invoice_date,
                            "status": "success",
                            "message": posting_message,
                            "doc_entry": doc_entry,
                            "validation_result_id": validation_result_id
                        })
                    else:
                        error_message = invoice_resp.get("message", "Unknown error")
                        
                        self.update_posting_status(
                            automation_id=automation.id,
                            invoice_date=invoice_date,
                            posting_status=ValidationResult.PostingStatus.FAILED,
                            posting_message=f"Invoice creation failed: {error_message}",
                            validation_result_id=validation_result_id  # ✅ Pass ID
                        )
                        
                        all_invoices_created = False
                        invoice_errors.append(f"Invoice {invoice_date}: {error_message}")
                        
                        invoice_creation_results.append({
                            "invoice_date": invoice_date,
                            "status": "failed",
                            "message": error_message,
                            "doc_entry": None,
                            "validation_result_id": validation_result_id
                        })
                    # ========== END: UPDATE POSTING STATUS ==========
                
                elif len(validation_results) > 1:
                    # CASE 2 (1:many) OR CASE 4 (many:many) - Multiple invoices
                    print(f"Creating {len(validation_results)} separate invoices")
                    
                    for idx, validation_result in enumerate(validation_results):
                        validated_payload = validation_result.get("payload")
                        invoice_date = validation_result.get("invoice_date")
                        
                        # ✅ Get the corresponding validation_result_id for THIS specific invoice
                        validation_result_id = validation_result_ids[idx] if idx < len(validation_result_ids) else None
                        
                        print(f"\n{'='*60}")
                        print(f"Creating invoice {idx + 1}/{len(validation_results)}")
                        print(f"Invoice Date: {invoice_date}")
                        print(f"Validation Result ID: {validation_result_id}")
                        print(f"{'='*60}\n")
                        
                        invoice_resp = create_invoice(validated_payload, use_dummy=True)
                        print(f"Invoice {idx + 1} Response:")
                        print(invoice_resp)
                        
                        # ========== UPDATE POSTING STATUS ==========
                        if invoice_resp.get("status") == "success":
                            doc_entry = invoice_resp.get("data", {}).get("DocEntry")
                            posting_message = f"Invoice {idx + 1} created successfully. DocEntry: {doc_entry}"
                            
                            update_success = self.update_posting_status(
                                automation_id=automation.id,
                                invoice_date=invoice_date,
                                posting_status=ValidationResult.PostingStatus.POSTED,
                                posting_message=posting_message,
                                validation_result_id=validation_result_id  # ✅ Pass ID
                            )
                            
                            if not update_success:
                                logger.error(
                                    f"❌ Failed to update posting status for invoice {idx + 1} "
                                    f"(validation_result_id: {validation_result_id})"
                                )
                            
                            invoice_creation_results.append({
                                "invoice_date": invoice_date,
                                "status": "success",
                                "message": posting_message,
                                "doc_entry": doc_entry,
                                "validation_result_id": validation_result_id
                            })
                        else:
                            error_message = invoice_resp.get("message", "Unknown error")
                            
                            update_success = self.update_posting_status(
                                automation_id=automation.id,
                                invoice_date=invoice_date,
                                posting_status=ValidationResult.PostingStatus.FAILED,
                                posting_message=f"Invoice {idx + 1} creation failed: {error_message}",
                                validation_result_id=validation_result_id  # ✅ Pass ID
                            )
                            
                            if not update_success:
                                logger.error(
                                    f"❌ Failed to update posting status for invoice {idx + 1} "
                                    f"(validation_result_id: {validation_result_id})"
                                )
                            
                            all_invoices_created = False
                            invoice_errors.append(f"Invoice {idx + 1} ({invoice_date}): {error_message}")
                            
                            invoice_creation_results.append({
                                "invoice_date": invoice_date,
                                "status": "failed",
                                "message": error_message,
                                "doc_entry": None,
                                "validation_result_id": validation_result_id
                            })
                        # ========== END: UPDATE POSTING STATUS ==========
    
                
                # Create final booking step
                if all_invoices_created:
                    if len(invoice_creation_results) == 1:
                        message = f"Invoice created successfully. {invoice_creation_results[0]['message']}"
                    else:
                        message = f"Created {len(invoice_creation_results)} invoices successfully"
                    
                    self.create_step(
                        automation=automation,
                        step_name=AutomationStep.Step.BOOKED,
                        status=AutomationStep.Status.SUCCESS,
                        message=message
                    )
                    
                    automation.status = GRNAutomation.Status.COMPLETED
                    automation.completed_at = timezone.now()
                    automation.save(update_fields=["status", "completed_at"])
                    
                    return Response({
                        "success": True,
                        "message": f"Your {self.case_type.replace('_', ' ')} automation completed successfully.",
                        "automation_status": automation.status,
                        "invoices_created": len(invoice_creation_results),
                        "invoice_details": invoice_creation_results,
                        "raw_data": markdown_text,
                        "vendor_data": vendor_info,
                        "all_open_grns": all_open_grns,
                        "filtered_grns": filtered_grns,
                        "matched_grns": matched_grns,
                        "validated_data": validated_grns,
                    }, status=status.HTTP_201_CREATED)
                
                else:
                    self.create_step(
                        automation=automation,
                        step_name=AutomationStep.Step.BOOKED,
                        status=AutomationStep.Status.FAILED,
                        message="; ".join(invoice_errors)
                    )
                    
                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])
                    
                    return Response({
                        "success": False,
                        "message": f"Invoice creation failed: {'; '.join(invoice_errors)}",
                        "automation_status": automation.status,
                        "invoices_attempted": len(validation_results),
                        "invoices_created": len([r for r in invoice_creation_results if r["status"] == "success"]),
                        "errors": invoice_errors,
                        "invoice_details": invoice_creation_results,
                    }, status=status.HTTP_400_BAD_REQUEST)

            except Exception as e:
                logger.error(f"Unexpected error during invoice creation: {str(e)}", exc_info=True)
                
                # Update posting status to failed for all validation results
                for validation_result in validation_results:
                    self.update_posting_status(
                        automation_id=automation.id,
                        invoice_date=validation_result.get("invoice_date"),
                        posting_status=ValidationResult.PostingStatus.FAILED,
                        posting_message=f"Unexpected error: {str(e)}"
                    )
                
                self.create_step(
                    automation=automation,
                    step_name=AutomationStep.Step.BOOKED,
                    status=AutomationStep.Status.FAILED,
                    message=f"Unexpected error: {str(e)}"
                )
                
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                
                return Response({
                    "success": False,
                    "message": f"Invoice creation error: {str(e)}",
                    "automation_status": automation.status,
                    "error_type": type(e).__name__,
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OneToOneAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_ONE


class OneToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_MANY


class ManyToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.MANY_TO_MANY


# from .tasks import process_grn_automation  # 👈 Import the Celery task

# class BaseAutomationUploadView(APIView):
#     permission_classes = [IsAuthenticated]
#     case_type = GRNAutomation.CaseType.ONE_TO_ONE

#     def post(self, request, *args, **kwargs):
#         data = request.data if isinstance(request.data, dict) else request.data.dict()

#         serializer = AutomationUploadSerializer(data=data, context={"request": request})
#         if serializer.is_valid():
#             automation = serializer.save()
#             automation.file.close()

#             # Trigger async processing
#             process_grn_automation.delay(automation.id)

#             return Response({
#                 "success": True,
#                 "message": f"Your {self.case_type.replace('_', ' ')} automation has been queued for processing.",
#                 # "automation_id": automation.id,
#             }, status=status.HTTP_202_ACCEPTED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreateInvoiceView(APIView):
    """
    Endpoint: POST /api/invoices/create
    
    Creates A/P Invoice in SAP B1 from one or more GRPOs.
    
    Supports three scenarios:
    1. One GRN to One Invoice (1:1)
    2. One GRN to Multiple Invoices (1:many)
    3. Multiple GRNs to One Invoice (many:1)
    
    Request Body:
        - grns: Single GRN object or array of GRN objects
        - use_dummy: Optional boolean (default: False) for testing
    
    Response:
        - status: "success" or "failed"
        - message: Description of result
        - data: Invoice data or None on failure
    """

    def post(self, request, *args, **kwargs):
        try:
            # Extract payload from request
            grn_payload = request.data.get("grns")
            use_dummy = request.data.get("use_dummy", False)
            
            # Validation: Check if grns data is provided
            if not grn_payload:
                return Response(
                    {
                        "status": "failed",
                        "message": "Missing 'grns' field in request body",
                        "data": None
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(f"Received invoice creation request with use_dummy={use_dummy}")
            logger.debug(f"GRN payload: {grn_payload}")
            
            # Call create_invoice service
            result = create_invoice(grn_payload, use_dummy=use_dummy)
            
            # Return appropriate response based on result
            if result["status"] == "success":
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error("Unexpected error in CreateInvoiceView: %s", str(e), exc_info=True)
            return Response(
                {
                    "status": "failed",
                    "message": f"Server error: {str(e)}",
                    "data": None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BranchListView(APIView):
    """
    Endpoint: GET /api/branches/
    Fetch all active branches from SAP B1
    """

    def get(self, request, *args, **kwargs):
        try:
            SAPService.ensure_session()

            url = f"{SERVICE_LAYER_URL}/BusinessPlaces"
            headers = {
                "Cookie": f"B1SESSION={SAPService.session_id}",
                "Content-Type": "application/json",
            }

            resp = requests.get(url, headers=headers, verify=False, timeout=30)

            if resp.status_code == 200:
                return Response(
                    {"status": "success", "data": resp.json().get("value", [])},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {
                        "status": "failed",
                        "message": f"SAP Error: {resp.text}",
                        "data": None,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        except Exception as e:
            logger.error("Error fetching branches: %s", str(e), exc_info=True)
            return Response(
                {"status": "failed", "message": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VendorGRNView(APIView):
    """
    API endpoint to fetch open GRNs for a given vendor.
    """

    def post(self, request):
        serializer = VendorCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "failed", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor_code = serializer.validated_data["vendor_code"]
        result = fetch_grns_for_vendor(vendor_code)

        if result["status"] == "success":
            return Response(result, status=status.HTTP_200_OK)
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorFilterOpenGRNView(APIView):
    """
    API endpoint to fetch and filter open GRNs for a given vendor.
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = VendorCodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "failed", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor_code = serializer.validated_data["vendor_code"]

        # Fetch raw GRNs from SAP
        fetch_result = fetch_grns_for_vendor(vendor_code)
        if fetch_result["status"] != "success":
            return Response(fetch_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        raw_grns = fetch_result.get("data", [])

        # Apply filtering to each GRN
        filtered_grns = []
        for grn in raw_grns:
            filter_result = filter_grn_response(grn)
            if filter_result["status"] == "success":
                filtered_grns.append(filter_result["data"])
            else:
                # You could choose to skip or stop; here we skip failed ones
                continue

        return Response(
            {
                "status": "success",
                "message": f"Fetched and filtered {len(filtered_grns)} open GRNs for vendor {vendor_code}.",
                "data": filtered_grns,
            },
            status=status.HTTP_200_OK,
        )


class VendorGRNMatchView(APIView):
    """
    API endpoint to fetch open GRNs for a vendor,
    filter them, and match against provided PO numbers.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GRNMatchRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"status": "failed", "message": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor_code = serializer.validated_data["vendor_code"]
        grn_po = serializer.validated_data["grn_po"]

        # Step 1: Fetch open GRNs
        fetch_result = fetch_grns_for_vendor(vendor_code)
        if fetch_result["status"] != "success":
            return Response(fetch_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        raw_grns = fetch_result.get("data", [])

        # Step 2: Filter GRNs
        filtered_grns = []
        for grn in raw_grns:
            filter_result = filter_grn_response(grn)
            if filter_result["status"] == "success" and filter_result["data"]:
                filtered_grns.append(filter_result["data"])

        if not filtered_grns:
            return Response(
                {
                    "status": "failed",
                    "message": f"No open GRNs found for vendor {vendor_code}.",
                    "data": None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Step 3: Match GRNs with PO numbers
        match_result = matching_grns(vendor_code, grn_po, filtered_grns)

        if match_result["status"] == "success":
            return Response(match_result, status=status.HTTP_200_OK)

        return Response(match_result, status=status.HTTP_404_NOT_FOUND)


class TotalStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days_value = request.query_params.get("days")
        if days_value is None or not days_value.strip():
            days = 1
        else:
            try:
                days = int(days_value.strip())
                if days not in (1, 5, 7):
                    return Response(
                        {"error": "Invalid days parameter. Only 1, 5, or 7 are allowed."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except ValueError:
                return Response(
                    {"error": "Invalid days parameter. Only 1, 5, or 7 are allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        result = get_total_stats(user=request.user, days=days)
        serialized = TotalStatsSerializer(result)
        return Response(serialized.data, status=status.HTTP_200_OK)


class CaseTypeStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_type):
        days_value = request.query_params.get("days")
        if days_value is None or not days_value.strip():
            days = 1
        else:
            try:
                days = int(days_value.strip())
                if days not in (1, 5, 7):
                    return Response(
                        {"error": "Invalid days parameter. Only 1, 5, or 7 are allowed."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except ValueError:
                return Response(
                    {"error": "Invalid days parameter. Only 1, 5, or 7 are allowed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if not case_type:
            result = get_case_type_stats(None, user=request.user, days=days)
            serialized = CaseTypeStatsSerializer(result)
            return Response(serialized.data, status=status.HTTP_200_OK)

        if case_type not in GRNAutomation.CaseType.values:
            return Response(
                {"error": "Invalid case_type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = get_case_type_stats(case_type, user=request.user, days=days)
        serialized = CaseTypeStatsSerializer(result)
        return Response(serialized.data, status=status.HTTP_200_OK)
    

class PurchaseInvoiceDetailView(APIView):
    """
    Retrieve a specific Purchase Invoice by DocNum and optionally CardCode.
    
    Query Parameters:
    - card_code: Vendor code (highly recommended for accuracy)
    - select: Comma-separated fields (e.g., DocEntry,DocNum,DocType)
    
    Examples:
    GET /api/purchase-invoices/12342/
    GET /api/purchase-invoices/12342/?card_code=V00001
    GET /api/purchase-invoices/12342/?card_code=V00001&select=DocEntry,DocNum,DocType,CardCode,CardName
    """
    
    def get(self, request, doc_num):
        # Get query parameters
        card_code = request.query_params.get('card_code', None)
        select_fields = request.query_params.get('select', None)
        
        # Fetch purchase invoice from SAP
        result = fetch_purchase_invoice_by_docnum(
            doc_num=doc_num,
            card_code=card_code,
            select_fields=select_fields
        )
        
        if result["status"] == "success":
            return Response(
                {
                    "status": result["status"],
                    "message": result["message"],
                    "data": result["data"]
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    "status": result["status"],
                    "message": result["message"],
                    "data": result["data"]
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        

class AutomationInvoicesListView(APIView):
    """
    GET: List all invoices (validation results) for a specific automation
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, automation_id):
        """
        Get all validation results (invoices) for a specific automation.
        
        Query Parameters:
            - posting_status: Filter by posting status (pending/posted/failed)
            - validation_status: Filter by validation status (SUCCESS/FAILED/PARTIAL)
        """
        try:
            # Verify automation exists and belongs to user
            automation = get_object_or_404(
                GRNAutomation,
                id=automation_id,
                user=request.user
            )
            
            # Base queryset with related data
            queryset = ValidationResult.objects.filter(
                automation=automation
            ).prefetch_related('document_lines')
            
            # Apply filters
            posting_status = request.query_params.get('posting_status')
            if posting_status:
                queryset = queryset.filter(posting_status=posting_status)
            
            validation_status = request.query_params.get('validation_status')
            if validation_status:
                queryset = queryset.filter(validation_status=validation_status)
            
            # Serialize and return
            serializer = ValidationResultListSerializer(queryset, many=True)
            
            return Response({
                'success': True,
                'automation_id': automation_id,
                'automation_status': automation.status,
                'case_type': automation.case_type,
                'total_invoices': queryset.count(),
                'invoices': serializer.data
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error fetching invoices for automation {automation_id}: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f"Error fetching invoices: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InvoiceDetailView(APIView):
    """
    GET: Retrieve a single invoice (validation result)
    PUT/PATCH: Update invoice data (only if not posted)
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, invoice_id):
        """
        Get detailed information about a specific invoice.
        """
        try:
            # Get validation result with related data
            validation_result = get_object_or_404(
                ValidationResult.objects.select_related('automation').prefetch_related('document_lines'),
                id=invoice_id,
                automation__user=request.user  # Ensure user owns the automation
            )
            
            serializer = ValidationResultSerializer(validation_result)
            
            return Response({
                'success': True,
                'invoice': serializer.data
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error fetching invoice {invoice_id}: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f"Error fetching invoice: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request, invoice_id):
        """
        Update invoice data (only if posting_status is not 'posted').
        
        Only existing document lines can be updated. Creating new lines is not allowed.
        """
        try:
            # Get validation result
            validation_result = get_object_or_404(
                ValidationResult.objects.prefetch_related('document_lines'),
                id=invoice_id,
                automation__user=request.user
            )
            
            # Check if already posted
            if validation_result.posting_status == ValidationResult.PostingStatus.POSTED:
                return Response({
                    'success': False,
                    'message': 'Cannot update invoice that has already been posted',
                    'invoice_id': invoice_id,
                    'posting_status': 'posted'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Validate and update
            serializer = ValidationResultUpdateSerializer(
                validation_result,
                data=request.data,
                partial=True
            )
            
            if serializer.is_valid():
                serializer.save()
                
                # Return updated data
                response_serializer = ValidationResultSerializer(validation_result)
                
                return Response({
                    'success': True,
                    'message': 'Invoice updated successfully',
                    'invoice': response_serializer.data
                }, status=status.HTTP_200_OK)
            
            # Validation failed - serializer.errors contains the errors
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            logger.error(f"Error updating invoice {invoice_id}: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f"Error updating invoice: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request, invoice_id):
        """Full update - same as PATCH for this use case"""
        return self.patch(request, invoice_id)


class InvoiceRetryView(APIView):
    """
    POST: Retry creating an invoice for a failed/pending validation result
    Automatically updates posting_status and posting_message based on create_invoice response
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, invoice_id):
        """
        Retry invoice creation for a specific validation result.
        Automatically updates posting_status and posting_message.
        
        Request body (optional):
        {
            "use_dummy": true/false  # Default: false
        }
        """
        try:
            from grn_automation.utils.invoice import create_invoice
            
            # Get validation result
            validation_result = get_object_or_404(
                ValidationResult.objects.select_related('automation').prefetch_related('document_lines'),
                id=invoice_id,
                automation__user=request.user
            )
            
            # Check if already posted
            if validation_result.posting_status == ValidationResult.PostingStatus.POSTED:
                return Response({
                    'success': False,
                    'message': 'Invoice already posted successfully. Cannot retry.',
                    'invoice_id': invoice_id,
                    'posting_status': 'posted',
                    'doc_entry': validation_result.doc_entry
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Build payload from current validation result data
            payload = {
                'CardCode': validation_result.card_code,
                'DocEntry': validation_result.doc_entry,
                'DocDate': validation_result.doc_date.strftime('%Y-%m-%d'),
                'BPL_IDAssignedToInvoice': validation_result.bpl_id,
                'DocumentLines': [
                    {
                        'LineNum': line.line_num,
                        'RemainingOpenQuantity': float(line.remaining_open_quantity)
                    }
                    for line in validation_result.document_lines.all()
                ]
            }
            
            # Get use_dummy from request or default to False
            use_dummy = request.data.get('use_dummy', True)
            
            logger.info(f"Retrying invoice creation for ValidationResult {invoice_id}")
            logger.debug(f"Payload: {payload}")
            
            # Attempt to create invoice
            invoice_resp = create_invoice(payload, use_dummy=use_dummy)
            
            # ========== AUTO UPDATE POSTING STATUS BASED ON RESPONSE ==========
            if invoice_resp.get('status') == 'success':
                # SUCCESS: Update to POSTED
                doc_entry = invoice_resp.get('data', {}).get('DocEntry')
                validation_result.posting_status = ValidationResult.PostingStatus.POSTED
                validation_result.posting_message = (
                    f"Invoice created successfully on retry. DocEntry: {doc_entry}"
                )
                validation_result.save(update_fields=['posting_status', 'posting_message', 'updated_at'])
                
                logger.info(f"✅ Invoice {invoice_id} posted successfully. DocEntry: {doc_entry}")
                
                return Response({
                    'success': True,
                    'message': 'Invoice created successfully',
                    'invoice_id': invoice_id,
                    'doc_entry': doc_entry,
                    'posting_status': 'posted',
                    'posting_message': validation_result.posting_message,
                    'invoice_response': invoice_resp
                }, status=status.HTTP_201_CREATED)
            else:
                # FAILED: Update to FAILED
                error_message = invoice_resp.get('message', 'Unknown error')
                validation_result.posting_status = ValidationResult.PostingStatus.FAILED
                validation_result.posting_message = f"Retry failed: {error_message}"
                validation_result.save(update_fields=['posting_status', 'posting_message', 'updated_at'])
                
                logger.error(f"❌ Invoice {invoice_id} creation failed: {error_message}")
                
                return Response({
                    'success': False,
                    'message': f"Invoice creation failed: {error_message}",
                    'invoice_id': invoice_id,
                    'posting_status': 'failed',
                    'posting_message': validation_result.posting_message,
                    'invoice_response': invoice_resp
                }, status=status.HTTP_400_BAD_REQUEST)
            # ========== END: AUTO UPDATE POSTING STATUS ==========
        
        except Exception as e:
            logger.error(f"Error retrying invoice {invoice_id}: {str(e)}", exc_info=True)
            
            # Update status to failed on exception
            try:
                validation_result = ValidationResult.objects.get(id=invoice_id)
                validation_result.posting_status = ValidationResult.PostingStatus.FAILED
                validation_result.posting_message = f"Retry error: {str(e)}"
                validation_result.save(update_fields=['posting_status', 'posting_message', 'updated_at'])
            except:
                pass
            
            return Response({
                'success': False,
                'message': f"Error retrying invoice: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AutomationInvoiceStatsView(APIView):
    """
    GET: Get statistics for invoices in an automation
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, automation_id):
        """
        Get invoice statistics for an automation.
        
        Returns counts by posting_status and validation_status.
        """
        try:
            # Verify automation exists and belongs to user
            automation = get_object_or_404(
                GRNAutomation,
                id=automation_id,
                user=request.user
            )
            
            # Get all validation results
            validation_results = ValidationResult.objects.filter(automation=automation)
            
            # Calculate stats
            total_count = validation_results.count()
            posted_count = validation_results.filter(posting_status=ValidationResult.PostingStatus.POSTED).count()
            failed_count = validation_results.filter(posting_status=ValidationResult.PostingStatus.FAILED).count()
            pending_count = validation_results.filter(posting_status=ValidationResult.PostingStatus.PENDING).count()
            
            validation_success = validation_results.filter(validation_status=ValidationResult.ValidationStatus.SUCCESS).count()
            validation_failed = validation_results.filter(validation_status=ValidationResult.ValidationStatus.FAILED).count()
            
            return Response({
                'success': True,
                'automation_id': automation_id,
                'automation_status': automation.status,
                'case_type': automation.case_type,
                'statistics': {
                    'total_invoices': total_count,
                    'posting_status': {
                        'posted': posted_count,
                        'failed': failed_count,
                        'pending': pending_count
                    },
                    'validation_status': {
                        'success': validation_success,
                        'failed': validation_failed
                    },
                    'completion_rate': f"{(posted_count / total_count * 100):.2f}%" if total_count > 0 else "0.00%"
                }
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error fetching stats for automation {automation_id}: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'message': f"Error fetching statistics: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
