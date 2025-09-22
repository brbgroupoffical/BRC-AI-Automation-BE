import logging
import requests
import os
from datetime import date
from sap_integration.sap_service import SAPService

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def create_invoice(grns):
    """
    Create A/P Invoice in SAP B1 (supports both single and multiple GRNs).
    Returns dict with keys: status, message, data
    """
    try:
        SAPService.ensure_session()

        # Ensure GRNs is a list (wrap if it's a single dict)
        if isinstance(grns, dict):
            grns = [grns]

        if not grns:
            return {
                "status": "failed",
                "message": "No GRN data provided.",
                "data": None
            }

        # Optional: Ensure all GRNs have the same CardCode (vendor)
        card_codes = {grn.get("CardCode") for grn in grns}
        if len(card_codes) > 1:
            return {
                "status": "failed",
                "message": "Multiple vendors found in GRNs. Cannot create single invoice.",
                "data": None
            }

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

        if not doc_lines:
            return {
                "status": "failed",
                "message": "No valid document lines found in GRNs.",
                "data": None
            }

        payload = {
            "CardCode": grns[0].get("CardCode"),
            "DocDate": date.today().isoformat(),
            "DocumentLines": doc_lines,
        }

        # -------------------------------
        # 🔁 TOGGLE: Real SAP call vs Dummy
        # -------------------------------
        # Uncomment below for real SAP call
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

        # Dummy response (for testing)
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


# Date Format DD/MM/YYYY
# "DocDate": "2025-09-20",       // Document Date  // Invoice Date
# "TaxDate": "2025-09-22",       // Posting Date   // Current Date
# "DocDueDate": "2025-10-20",    // Due Date       // Auto Calculate Don't Add


# payload = {
            # "CardCode": grns[0].get("CardCode"),
            # "DocDate": date.today().isoformat(),
            # "DocumentLines": doc_lines,
        # }


# Will be added in this payload.