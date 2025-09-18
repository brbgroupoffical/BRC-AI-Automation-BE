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
from datetime import timezone


logger = logging.getLogger(__name__)


class UserAutomationDetailView(RetrieveAPIView):
    """
    Retrieve details of a single automation job for the logged-in user.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure user can only see their own jobs
        return GRNAutomation.objects.filter(user=self.request.user)


class UserAutomationListView(ListAPIView):
    """
    List all automation jobs for the logged-in user.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return GRNAutomation.objects.filter(user=self.request.user).order_by("-created_at")


class BaseAutomationUploadView(APIView):
    permission_classes = [IsAuthenticated]
    case_type = GRNAutomation.CaseType.ONE_TO_ONE

    def post(self, request, *args, **kwargs):
        data = request.data.dict()
        data["case_type"] = self.case_type

        serializer = AutomationUploadSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            automation = serializer.save()
            automation.file.close()

            # always fetch single step row
            step = automation.steps.first()

            # mark automation as running
            automation.status = GRNAutomation.Status.RUNNING
            automation.save(update_fields=["status"])

            file_path = automation.file.path
            extractor = AWSTextractSAPExtractor()
            response = extractor.extract_sap_data(file_path)

            result_status = response["status"]
            message = response["message"]
            result = response["data"]

            # ---------- Extraction ----------
            step.step_name = AutomationStep.Step.EXTRACTION
            step.status = AutomationStep.Status.SUCCESS if result_status == "success" else AutomationStep.Status.FAILED
            step.message = message
            step.save()

            if result_status != "success" or not result:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Extraction failed: {message}"}, status=status.HTTP_400_BAD_REQUEST)

            vendor_name = result["sap_fields"].get("vendor_name")
            grn_po_number = result["sap_fields"].get("po_number")
            vendor_code = "S00274"  # TODO: replace with vendor lookup
            print(vendor_name, vendor_code)

            # ---------- Fetch GRNs ----------
            fetch_resp = fetch_grns_for_vendor(vendor_code)
            step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
            step.status = AutomationStep.Status.SUCCESS if fetch_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = fetch_resp["message"]
            step.save()

            if fetch_resp["status"] != "success" or not fetch_resp["data"]:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"GRN fetch failed: {fetch_resp['message']}"}, status=status.HTTP_400_BAD_REQUEST)

            all_open_grns = fetch_resp["data"]

            # ---------- Filter + Matching ----------
            try:
                filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
                matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)

                step.step_name = AutomationStep.Step.VALIDATION  # preparing for validation
                step.status = AutomationStep.Status.SUCCESS
                step.message = f"Found {len(matched_grns)} matching GRNs."
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
            validation_resp = validate_invoice_with_grn(result, matched_grns)

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

            step.step_name = AutomationStep.Step.BOOKED
            step.status = AutomationStep.Status.SUCCESS if invoice_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = invoice_resp["message"]
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
                "automation_status": automation.status,
                "step": {
                    "id": step.id,
                    "step_name": step.step_name,
                    "status": step.status,
                    "updated_at": step.updated_at,
                    "message": step.message
                },
                "validated_data": validated_grns,
                "invoice": invoice_resp["data"]
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OneToOneAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_ONE


class OneToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_MANY


class ManyToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.MANY_TO_MANY
