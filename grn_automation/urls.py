from django.urls import path
from .views import UserAutomationListView,  UserAutomationDetailView
from .views import (
    OneToOneAutomationUploadView,
    OneToManyAutomationUploadView,
    ManyToManyAutomationUploadView,
)
from .views import CreateInvoiceView


urlpatterns = [
    path("automation-details/", UserAutomationListView.as_view(), name="user-automations"),
    path("automation-details/<int:pk>/", UserAutomationDetailView.as_view(), name="user-automation-detail"),



    path("upload/one-to-one/", OneToOneAutomationUploadView.as_view(), name="upload-one-to-one"),
    path("upload/one-to-many/", OneToManyAutomationUploadView.as_view(), name="upload-one-to-many"),
    path("upload/many-to-many/", ManyToManyAutomationUploadView.as_view(), name="upload-many-to-many"),

    path("invoices/create/", CreateInvoiceView.as_view(), name="create-invoice"),
]


