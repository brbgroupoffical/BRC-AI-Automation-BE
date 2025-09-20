import os
import requests
from sap_integration.sap_service import SAPService

SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


class SAPAttachmentService:
    @staticmethod
    def upload_attachment(file_obj, filename: str):
        """
        Uploads a file to SAP B1 Attachments2 endpoint.
        """
        SAPService.ensure_session()

        url = f"{SERVICE_LAYER_URL}/Attachments2"
        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
        }
        files = {
            "files": (filename, file_obj, "application/octet-stream")
        }

        try:
            resp = requests.post(url, headers=headers, files=files, verify=False, timeout=30)
            resp.raise_for_status()
            return {"status": "success", "data": resp.json()}
        except requests.RequestException as e:
            return {"status": "failed", "message": str(e), "data": None}

    @staticmethod
    def get_attachment(attachment_id: int):
        """
        Fetches metadata/details of an attachment.
        """
        SAPService.ensure_session()

        url = f"{SERVICE_LAYER_URL}/Attachments2({attachment_id})"
        headers = {"Cookie": f"B1SESSION={SAPService.session_id}"}

        try:
            resp = requests.get(url, headers=headers, verify=False, timeout=15)
            resp.raise_for_status()
            return {"status": "success", "data": resp.json()}
        except requests.RequestException as e:
            return {"status": "failed", "message": str(e), "data": None}

    @staticmethod
    def delete_attachment(attachment_id: int):
        """
        Deletes an attachment by ID.
        """
        SAPService.ensure_session()

        url = f"{SERVICE_LAYER_URL}/Attachments2({attachment_id})"
        headers = {"Cookie": f"B1SESSION={SAPService.session_id}"}

        try:
            resp = requests.delete(url, headers=headers, verify=False, timeout=15)
            resp.raise_for_status()
            return {"status": "success", "message": "Attachment deleted successfully"}
        except requests.RequestException as e:
            return {"status": "failed", "message": str(e)}
