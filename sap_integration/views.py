import time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .sap_service import SAPService


class SAPHealthCheckView(APIView):
    """
    Health endpoint to check SAP connection, session, and basic company info.
    """

    def get(self, request):
        relogin_triggered = False
        company_info = None

        try:
            # Ensure session (this may trigger a re-login if expired)
            old_session = SAPService.session_id
            session_id = SAPService.ensure_session()
            if old_session != session_id:
                relogin_triggered = True

            # Session age
            age = None
            expiry_status = "unknown"
            if SAPService.session_created_at:
                age = round(time.time() - SAPService.session_created_at, 2)
                expiry_status = (
                    "valid"
                    if age < SAPService.SESSION_TIMEOUT
                    else "expired-but-reusable"
                )

            # Fetch company info from SAP (optional deeper check)
            try:
                company_info = SAPService.get_company_info()
            except Exception as e:
                company_info = {"error": str(e)}

            return Response(
                {
                    "sap_connected": True,
                    "session_id": session_id,
                    "session_age_seconds": age,
                    "expiry_status": expiry_status,
                    "relogin_triggered": relogin_triggered,
                    "company_info": company_info,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {
                    "sap_connected": False,
                    "error": str(e),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
