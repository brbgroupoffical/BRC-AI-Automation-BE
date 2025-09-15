from django.urls import path
from .views import SAPHealthCheckView

urlpatterns = [
    path("health/", SAPHealthCheckView.as_view(), name="sap-health"),
]
