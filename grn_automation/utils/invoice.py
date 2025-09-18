import logging
from sap_integration.sap_service import SAPService
import requests, os
from datetime import date

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def create_invoice(grns):
    """
    Create A/P Invoice in SAP B1 (dummy for testing).
    Returns dict with keys: status, message, data
    """
    try:
        SAPService.ensure_session()
        doc_lines = []
        for grn in grns:
            for line in grn.get("DocumentLines", []):
                doc_lines.append({
                    "BaseType": line.get("BaseType"),
                    "BaseEntry": line.get("BaseEntry"),
                    "BaseLine": line.get("BaseLine"),
                    "Quantity": line.get("Quantity", 0),
                    "UnitPrice": line.get("UnitPrice", 0.0),
                })

        payload = {
            "CardCode": grns[0].get("CardCode"),
            "DocDate": date.today().isoformat(),  # dynamic date
            "DocumentLines": doc_lines,
        }

        # --- Commented out real SAP call for testing ---
        # headers = {
        #     "Cookie": f"B1SESSION={SAPService.session_id}",
        #     "Content-Type": "application/json",
        # }
        # url = f"{SERVICE_LAYER_URL}/PurchaseInvoices"
        # resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=30)
        # resp.raise_for_status()
        # return {
        #     "status": "success",
        #     "message": "Invoice created successfully",
        #     "data": resp.json(),
        # }

        # --- Dummy success response for testing ---
        return {
            "status": "success",
            "message": "Invoice created successfully (dummy)",
            "data": {
                "DocEntry": 12345,
                "CardCode": payload["CardCode"],
                "DocDate": payload["DocDate"],
                "LinesCount": len(doc_lines),
            },
        }

    except Exception as e:
        logger.error("Unexpected error while creating invoice: %s", e, exc_info=True)
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(e)}",
            "data": None,
        }
