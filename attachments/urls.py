from django.urls import path
from .views import AttachmentUploadView, AttachmentDetailView

urlpatterns = [
    path("attachments/upload/", AttachmentUploadView.as_view(), name="attachment-upload"),
    path("attachments/<int:pk>/", AttachmentDetailView.as_view(), name="attachment-detail"),
]
