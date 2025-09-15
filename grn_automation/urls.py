from django.urls import path
from .views import UserAutomationListView,  UserAutomationDetailView, AutomationUploadView


urlpatterns = [
    path("automation-details/", UserAutomationListView.as_view(), name="user-automations"),
    path("automation-details/<int:pk>/", UserAutomationDetailView.as_view(), name="user-automation-detail"),

    path('upload/', AutomationUploadView.as_view(), name='automation-upload'),
]
