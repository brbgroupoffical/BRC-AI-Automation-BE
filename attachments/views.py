from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .serializers import AttachmentUploadSerializer
from .services.sap_attachments_service import SAPAttachmentService


class AttachmentUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AttachmentUploadSerializer(data=request.data)
        if serializer.is_valid():
            file_obj = serializer.validated_data["file"]
            result = SAPAttachmentService.upload_attachment(file_obj, file_obj.name)
            return Response(result, status=status.HTTP_200_OK if result["status"] == "success" else status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AttachmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        result = SAPAttachmentService.get_attachment(pk)
        return Response(result, status=status.HTTP_200_OK if result["status"] == "success" else status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk: int):
        result = SAPAttachmentService.delete_attachment(pk)
        return Response(result, status=status.HTTP_200_OK if result["status"] == "success" else status.HTTP_400_BAD_REQUEST)
