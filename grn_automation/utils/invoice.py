import logging
import requests
import os
from datetime import date, timedelta
from sap_integration.sap_service import SAPService

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def create_invoice(grns, use_dummy=False):
    """
    Create A/P Invoice in SAP B1 (GRPO-based).
    - Uses RemainingOpenQuantity if available
    - Skips lines with no remaining qty
    - Supports dummy response for testing
    Returns dict with keys: status, message, data
    """
    try:
        SAPService.ensure_session()

        # Ensure GRNs is a list
        if isinstance(grns, dict):
            grns = [grns]

        if not grns:
            return {
                "status": "failed",
                "message": "No GRN data provided.",
                "data": None,
            }

        # Ensure same vendor
        card_codes = {grn.get("CardCode") for grn in grns}
        if len(card_codes) > 1:
            return {
                "status": "failed",
                "message": "Multiple vendors found in GRNs. Cannot create single invoice.",
                "data": None,
            }

        # Build document lines (must have RemainingOpenQuantity > 0)
        doc_lines = []
        for grn in grns:
            for line in grn.get("DocumentLines", []):
                qty = (
                    line.get("RemainingOpenQuantity", 0)  # preferred
                    or line.get("OpenQuantity")        # fallback
                    or line.get("Quantity", 0)         # fallback
                )
                if qty and qty > 0:
                    doc_lines.append({
                        "BaseType": line.get("BaseType"),   # always 20 for GRPO
                        "BaseEntry": line.get("BaseEntry"), # GRPO DocEntry
                        "BaseLine": line.get("BaseLine"),   # LineNum in GRPO
                        "Quantity": line.get("Quantity", 0),
                    })

        if not doc_lines:
            return {
                "status": "failed",
                "message": "All GRPO lines are fully invoiced or have no remaining open quantity.",
                "data": None,
            }

        # Dates
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        payload = {
            "CardCode": grns[0].get("CardCode"),
            "DocDate": today,                          # Invoice Date
            "TaxDate": today,  
            "DocDueDate": today,#                        # Posting Date
            #"DocDueDate": (today + timedelta(days=30)).isoformat(),# Due Date
            "DocumentLines": doc_lines
        }

        # -------------------------------
        # 🔁 Dummy mode (for testing)
        # -------------------------------
        if use_dummy:
            return {
                "status": "success",
                "message": "Invoice created successfully (dummy)",
                "data": {
                    "DocEntry": 99999,
                    "CardCode": payload["CardCode"],
                    "DocDate": payload["DocDate"],
                    "LinesCount": len(doc_lines),
                    "Lines": doc_lines,
                },
            }

        # -------------------------------
        # 🔁 Real SAP call
        # -------------------------------
        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
            "Content-Type": "application/json",
        }
        url = f"{SERVICE_LAYER_URL}/PurchaseInvoices"
        try:
            resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=30)
            resp.raise_for_status()

            return {
                "status": "success",
                "message": "Invoice created successfully",
                "data": resp.json(),
            }

        except requests.exceptions.HTTPError as http_err:
            # Capture error response (especially 400)
            error_text = resp.text if resp is not None else str(http_err)
            logger.error("HTTP error while creating invoice: %s", error_text, exc_info=True)
            return {
                "status": "failed",
                "message": f"HTTP error: {resp.status_code} - {error_text}",
                "data": None,
            }

    except Exception as e:
        logger.error("Unexpected error while creating invoice: %s", e, exc_info=True)
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(e)}",                
            "data": None,
        }

