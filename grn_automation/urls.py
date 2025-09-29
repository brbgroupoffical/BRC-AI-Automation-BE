from django.urls import path
from .views import UserAutomationListView,  UserAutomationDetailView, OneToOneAutomationUploadView, OneToManyAutomationUploadView, ManyToManyAutomationUploadView, CreateInvoiceView, BranchListView, VendorGRNView, VendorFilterOpenGRNView, VendorGRNMatchView
from .views import TotalStatsView, CaseTypeStatsView

urlpatterns = [
    path("upload/one-to-one/", OneToOneAutomationUploadView.as_view(), name="upload-one-to-one"),
    path("upload/one-to-many/", OneToManyAutomationUploadView.as_view(), name="upload-one-to-many"),
    path("upload/many-to-many/", ManyToManyAutomationUploadView.as_view(), name="upload-many-to-many"),

    path("automation-details/", UserAutomationListView.as_view(), name="user-automations"),
    path("automation-details/<int:pk>/", UserAutomationDetailView.as_view(), name="user-automation-detail"),

    path("branches/", BranchListView.as_view(), name="branch-list"),
    path("vendor-grns/", VendorGRNView.as_view(), name="vendor-grns"),
    path("vendor-filter-open-grns/", VendorFilterOpenGRNView.as_view(), name="vendor-filter-open-grns"),
    path("vendor-grn-match/", VendorGRNMatchView.as_view(), name="vendor-grn-match"),
    path("invoices/create/", CreateInvoiceView.as_view(), name="create-invoice"),

    path("automation/stats/total/", TotalStatsView.as_view(), name="automation-total-stats"),
    path("automation/stats/case-type/<str:case_type>/", CaseTypeStatsView.as_view(), name="automation-case-type-stats"),
]



