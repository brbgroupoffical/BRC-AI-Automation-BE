from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import AutomationUploadSerializer
from .models import AutomationStep
# from .tasks import run_pipeline
from django.contrib.auth.models import User
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation
from .serializers import GRNAutomationSerializer
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation
from .serializers import GRNAutomationSerializer


class UserAutomationDetailView(RetrieveAPIView):
    """
    Retrieve details of a single automation job for the logged-in user.
    """
    serializer_class = GRNAutomationSerializer
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure user can only see their own jobs
        return GRNAutomation.objects.filter(user=1)
        # return GRNAutomation.objects.filter(user=self.request.user)
    

class UserAutomationListView(ListAPIView):
    """
    List all automation jobs for the logged-in user.
    """
    serializer_class = GRNAutomationSerializer
    # permission_classes = [IsAuthenticated]  # 🔒 restrict to logged-in users

    def get_queryset(self):
        return GRNAutomation.objects.filter(user=1).order_by("-created_at")


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import AutomationUploadSerializer
from .models import AutomationStep
# from .tasks import run_full_automation
from .utils.extraction import AWSTextractSAPExtractor
from .utils.vendor import get_vendor_code_from_api
from .utils.grns import fetch_grns_for_vendor, filter_grn_response
from .utils.matcher import matching_grns

class AutomationUploadView(APIView):
    """
    Upload a GRN/Invoice file and start full automation.
    """

    def post(self, request, *args, **kwargs):
        serializer = AutomationUploadSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            automation = serializer.save()

            automation.file.close()   # ensure file is written

            # file_path = automation.file.path
            # print(file_path)
            # extractor = AWSTextractSAPExtractor()
            # result = extractor.extract_sap_data(file_path)

            result = {
                "sap_fields": {
                    # "vendor_code": 'S00274',
                    "vendor_code": 'S00166',
                    "po_number": 16064,
                    # "vendor_name": "JOTUN POWDER COATINGS S.A. CO. LTD"
                }
            }
            # Access SAP-specific fields
            #  have to change it to vendor code when changed remove it
            vendor_code = result['sap_fields'].get('vendor_code', None)
            vendor_name = result['sap_fields'].get('vendor_name', None)
            grn_po_number = result['sap_fields'].get('po_number')

            if not vendor_code:
                print("runnned")
                vendor_code = get_vendor_code_from_api(vendor_name)
                print(vendor_code)
            
            all_open_grns = fetch_grns_for_vendor(vendor_code)
            # print(all_open_grns)

            filtered_grns = [filter_grn_response(grn) for grn in all_open_grns]
            print(filtered_grns)


            matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)


            # Start Celery task
            # run_full_automation.delay(automation.id)

            return Response({
                "success": True,
                # "automation_id": automation.id,
                # "file": automation.file.url if automation.file else None,
                # "result": result,
                "all_open_grns": all_open_grns,
                "filtered_grns": filtered_grns,
                "matching_grns": matched_grns,
                "created_at": automation.created_at,
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

