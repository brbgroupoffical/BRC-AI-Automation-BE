import logging
from sap_integration.sap_service import SAPService
import requests, os

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def create_invoice(grns):
    """
    Create A/P Invoice in SAP B1.
    """
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
        "DocDate": "2025-09-12",  # you might want timezone.now().date().isoformat()
        "DocumentLines": doc_lines,
    }

    headers = {
        "Cookie": f"B1SESSION={SAPService.session_id}",
        "Content-Type": "application/json",
    }
    url = f"{SERVICE_LAYER_URL}/PurchaseInvoices"
    resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.json()
