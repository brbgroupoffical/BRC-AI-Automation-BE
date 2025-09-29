from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation, AutomationStep
from .serializers import AutomationUploadSerializer, GRNAutomationSerializer
from rest_framework.generics import RetrieveAPIView, ListAPIView
from .utils.extraction import AWSTextractSAPExtractor
from .utils.vendor import get_vendor_code_from_api
from .utils.grns import fetch_grns_for_vendor, filter_grn_response
from .utils.matcher import matching_grns
from .utils.invoice import create_invoice
from .utils.validation import validate_invoice_with_grn 
# from .tasks import run_full_automation
import logging
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import GRNAutomation
from .serializers import GRNAutomationSerializer
from .pagination import TenResultsSetPagination
from django.utils import timezone
from .utils.vision_extraction import PDFDataExtractor
import os
from sap_integration.sap_service import SAPService 
import requests
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
import os
from sap_integration.sap_service import SAPService  
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .utils.invoice import create_invoice 
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import VendorCodeSerializer, GRNMatchRequestSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import TotalStatsSerializer, CaseTypeStatsSerializer
from .services import get_total_stats, get_case_type_stats
from .models import GRNAutomation


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

            # always fetch single step row
            step = automation.steps.first()

            # mark automation as running
            automation.status = GRNAutomation.Status.RUNNING
            automation.save(update_fields=["status"])

            # ---------- SAP Login / VPN Check ----------
            try:
                SAPService.login()
                step.step_name = AutomationStep.Step.SAP_LOGIN
                step.status = AutomationStep.Status.SUCCESS
                step.message = "SAP/VPN connection successful. Logged in to SAP."
                step.save()
            except requests.exceptions.RequestException as e:
                step.step_name = AutomationStep.Step.SAP_LOGIN
                step.status = AutomationStep.Status.FAILED
                step.message = f"SAP/VPN connection failed."
                step.save()

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])

                return Response(
                    {"success": False, "message": f"SAP/VPN connection failed."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                step.step_name = AutomationStep.Step.SAP_LOGIN
                step.status = AutomationStep.Status.FAILED
                step.message = f"SAP login error."
                step.save()

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])

                return Response(
                    {"success": False, "message": f"SAP login error: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ---------- Extract Markdown ----------
            file_path = automation.file.path
            openai_api_key = os.getenv("OPENAI_API_KEY")
            extractor = PDFDataExtractor(api_key=openai_api_key)

            markdown_resp = extractor.extract_complete_markdown(file_path)
            if markdown_resp["status"] != "success" or not markdown_resp["data"]:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": f"Markdown extraction failed: {markdown_resp['message']}"
                }, status=status.HTTP_400_BAD_REQUEST)

            markdown_text = markdown_resp["data"]

            # ---------- Extract Vendor Fields ----------
            field_resp = extractor.extract_vendor_fields(markdown_text)
            if field_resp["status"] != "success" or not field_resp["data"]:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({
                    "success": False,
                    "message": f"Vendor field extraction failed: {field_resp['message']}"
                }, status=status.HTTP_400_BAD_REQUEST)

            # Old
            vendor_info = field_resp["data"]
            vendor_name = vendor_info.get("vendor_name", None)
            grn_po_number = vendor_info.get("grn_po_number", None)
            if grn_po_number:
                grn_po_number = int(grn_po_number)
            vendor_code = vendor_info.get("vendor_code", None)

            # New
            # vendor_info = field_resp["data"]["vendor_info"]
            # vendor_name = vendor_info.get("vendor_name", None)
            # grn_po_number = [int(i) for i in vendor_info.get("grn_po_number", [])]
            # vendor_code = vendor_info.get("vendor_code", None)

            print(f"Vendor Name: {vendor_name}, Vendor Code: {vendor_code}, PO Number: {grn_po_number}")
            print(f"Vendor Name: {type(vendor_name)}, Vendor Code: {type(vendor_code)}, PO Number: {type(grn_po_number)}")

            # ---------- Extraction Step ----------
            step.step_name = AutomationStep.Step.EXTRACTION
            step.status = AutomationStep.Status.SUCCESS
            step.message = "Extraction succeeded via OpenAI"
            step.save()

            if not any([vendor_name, grn_po_number, vendor_code]):
                step.step_name = AutomationStep.Step.GRN_DETAILS
                step.status = AutomationStep.Status.FAILED
                step.message = "No vendor name or grn po number or vendor code found."
                step.save()

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

                step.step_name = AutomationStep.Step.FETCH_OPEN_GRN  # Reusing step
                if vendor_code_resp["status"] != "success":
                    step.status = AutomationStep.Status.FAILED
                    step.message = vendor_code_resp["message"]
                    step.save()

                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])

                    return Response({
                        "success": False,
                        "message": f"Vendor code fetch failed: {vendor_code_resp['message']}"
                    }, status=status.HTTP_400_BAD_REQUEST)

                vendor_code = vendor_code_resp["data"]

            # ---------- Fetch GRNs ----------
            fetch_resp = fetch_grns_for_vendor(vendor_code)

            step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
            step.status = AutomationStep.Status.SUCCESS if fetch_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = fetch_resp["message"]
            step.save()

            # Check for failure or empty GRNs
            if fetch_resp["status"] != "success":
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response(
                    {"success": False, "message": f"{fetch_resp['message']}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Explicit check for empty GRNs
            if not fetch_resp["data"]:
                step.status = AutomationStep.Status.FAILED
                step.message = f"No open GRNs found for vendor {vendor_code}."
                step.save()

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])

                return Response(
                    {"success": False, "message": f"No open GRNs found for vendor {vendor_code}."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Continue if GRNs are found
            all_open_grns = fetch_resp["data"]
            print("Open GRNs")
            print(all_open_grns)

            # ---------- Filter + Matching ----------
            try:
                filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
                print("Filter")
                print(filtered_grns)

                matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)
                print("Matching")
                print(matched_grns)

                step.step_name = AutomationStep.Step.VALIDATION  # preparing for validation
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
                return Response({"success": False, "message": f"Matching failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Validation ----------
            validation_resp = validate_invoice_with_grn(markdown_text, matched_grns)

            print("Validaton")
            print(validation_resp)

            step.step_name = AutomationStep.Step.VALIDATION
            step.status = AutomationStep.Status.SUCCESS if validation_resp["status"] == "SUCCESS" else AutomationStep.Status.FAILED
            step.message = validation_resp["reasoning"]
            step.save()

            if validation_resp["status"] != "SUCCESS":
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Validation failed: {validation_resp['reasoning']}"}, status=status.HTTP_400_BAD_REQUEST)

            validated_grns = validation_resp["payload"]

            # ---------- Create Invoice ----------
            invoice_resp = create_invoice(validated_grns)
            print("Invoice")
            print(invoice_resp)

            step.step_name = AutomationStep.Step.BOOKED
            step.status = AutomationStep.Status.SUCCESS if invoice_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = f"{validation_resp['reasoning']} {invoice_resp['message']}"
            step.save()

            if invoice_resp["status"] != "success":
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Invoice creation failed: {invoice_resp['message']}"}, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Mark Completed ----------
            automation.status = GRNAutomation.Status.COMPLETED
            automation.completed_at = timezone.now()
            automation.save(update_fields=["status", "completed_at"])

            # ---------- Final Response ----------
            return Response({
                "success": True,
                "message": f"Your {self.case_type.replace('_', ' ')} automation has been queued successfully.",
                "automation_status": automation.status,
                "step": {
                    "id": step.id,
                    "step_name": step.step_name,
                    "status": step.status,
                    "updated_at": step.updated_at,
                    "message": step.message
                },
                "raw_data": markdown_text,
                "vendor_data": vendor_info,
                "all_open_grns": all_open_grns,
                "filtered_grns": filtered_grns,
                "matched_grns": matched_grns,
                "validated_data": validated_grns,
                "invoice_resp": invoice_resp,
                "invoice": invoice_resp["data"]
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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


class OneToOneAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_ONE


class OneToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_MANY


class ManyToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.MANY_TO_MANY


class CreateInvoiceView(APIView):
    """
    Endpoint: POST /api/invoices/create
    Payload: GRN(s) data for invoice creation
    """

    def post(self, request, *args, **kwargs):
        try:
            # Accept GRN payload directly from request body
            grn_payload = request.data
            grn_payload = {
                "CardCode": "S00166",
                "DocEntry": 20282,
                "DocDate": "2025-08-26",
                "BPL_IDAssignedToInvoice": 3,
                "DocumentLines": [
                    {
                        "LineNum": 0,
                        "RemainingOpenQuantity": 20.0
                    }
                ]
            }

            # Call create_invoice
            result = create_invoice(grn_payload, use_dummy=False)

            if result["status"] == "success":
                return Response(result, status=status.HTTP_201_CREATED)
            else:
                return Response(result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error("Error in CreateInvoiceView: %s", str(e), exc_info=True)
            return Response(
                {"status": "failed", "message": f"Server error: {str(e)}"},
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
        days = int(request.query_params.get("days", 1))
        if days not in [1, 5, 7]:
            days = 1

        stats = get_total_stats(user=request.user, days=days)
        return Response(TotalStatsSerializer(stats).data, status=status.HTTP_200_OK)


class CaseTypeStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_type):
        days = int(request.query_params.get("days", 1))
        if days not in [1, 5, 7]:
            days = 1

        if case_type not in GRNAutomation.CaseType.values:
            return Response({"error": "Invalid case_type"}, status=status.HTTP_400_BAD_REQUEST)

        stats = get_case_type_stats(case_type, user=request.user, days=days)
        return Response(CaseTypeStatsSerializer(stats).data, status=status.HTTP_200_OK)

