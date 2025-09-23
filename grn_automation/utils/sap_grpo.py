import logging
import requests
import os
from sap_integration.sap_service import SAPService

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def validate_grpo_by_vendor(card_code: str):
    """
    Fetch and validate open GRPOs (PurchaseDeliveryNotes) by Vendor Code (CardCode).
    Returns the full SAP response (all open GRPOs for that vendor).
    """
    try:
        SAPService.ensure_session()

        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
            "Content-Type": "application/json",
        }

        url = (
            f"{SERVICE_LAYER_URL}/PurchaseDeliveryNotes?"
            f"$filter=CardCode eq '{card_code}' and DocumentStatus eq 'bost_Open'"
            f"&$select=DocEntry,DocNum,DocDate,TaxDate,CreationDate,UpdateDate,"
            f"CardCode,CardName,DocTotal,DocTotalSys,DocCurrency,VatSum,"
            f"AddressExtension,TaxExtension,DocumentLines"
        )

        resp = requests.get(url, headers=headers, verify=False, timeout=30)

        if resp.status_code == 404:
            return {
                "status": "failed",
                "message": f"No open GRPOs found for vendor {card_code}.",
                "data": None,
            }

        resp.raise_for_status()
        grpo_data = resp.json()

        if "value" not in grpo_data or not grpo_data["value"]:
            return {
                "status": "failed",
                "message": f"No open GRPOs available for vendor {card_code}.",
                "data": grpo_data,
            }

        return {
            "status": "success",
            "message": f"Found {len(grpo_data['value'])} open GRPO(s) for vendor {card_code}.",
            "data": grpo_data,  # return full payload from SAP
        }

    except Exception as e:
        logger.error("Error while validating GRPO for vendor %s: %s", card_code, e, exc_info=True)
        return {
            "status": "failed",
            "message": f"Unexpected error while validating GRPO for vendor {card_code}: {str(e)}",
            "data": None,
        }
