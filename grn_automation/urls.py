from django.urls import path
from .views import UserAutomationListView,  UserAutomationDetailView, OneToOneAutomationUploadView, OneToManyAutomationUploadView, ManyToManyAutomationUploadView, CreateInvoiceView, BranchListView, VendorGRNView, VendorFilterOpenGRNView, VendorGRNMatchView
from .views import TotalStatsView, CaseTypeStatsView

from django.urls import path
from .views import PurchaseInvoiceDetailView


urlpatterns = [
    # In front end its GRN to Invoice - this is the actual convention
    # In BE its Invoice to GRN
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

    path("stats/total-automations/", TotalStatsView.as_view(), name="automation-total-stats"),
    path("stats/case-type/<str:case_type>/", CaseTypeStatsView.as_view(), name="automation-case-type-stats"),
     
    path('purchase-invoices/<str:doc_num>/', PurchaseInvoiceDetailView.as_view(), name='purchase-invoice-detail'),
]


# urls.py
from django.urls import path
from .views import (
    AutomationInvoicesListView,
    InvoiceDetailView,
    InvoiceRetryView
)

urlpatterns += [
    # List all invoices for an automation
    path(
        '<int:automation_id>/invoices/',
        AutomationInvoicesListView.as_view(),
        name='automation-invoices-list'
    ),
    
    # Get single invoice detail
    path(
        'invoices/<int:invoice_id>/',
        InvoiceDetailView.as_view(),
        name='invoice-detail'
    ),
    
    # Update single invoice (posting status/message)
    path(
        'invoices/<int:invoice_id>/update/',
        InvoiceDetailView.as_view(),
        name='invoice-update'
    ),
    
    # Retry failed invoice
    path(
        'invoices/<int:invoice_id>/retry/',
        InvoiceRetryView.as_view(),
        name='invoice-retry'
    ),
]