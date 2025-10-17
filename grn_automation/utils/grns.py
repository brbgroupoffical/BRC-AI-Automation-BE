import os
import requests
from sap_integration.sap_service import SAPService
import requests
import time


SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def fetch_grns_for_vendor(vendor_code, batch_size=10, max_retries=3, retry_delay=2):
    """
    Fetch open GRNs for a vendor in batches to avoid instability with large datasets.

    Args:
        vendor_code (str): The vendor code to filter GRNs.
        batch_size (int): Number of records to fetch per batch (default: 10).
        max_retries (int): Number of retries for transient errors.
        retry_delay (int): Delay in seconds between retries.

    Returns:
        dict: {status (str), message (str), data (list or None)}
    """
    if not vendor_code or not isinstance(vendor_code, str):
        return {
            "status": "failed",
            "message": "Invalid vendor_code provided.",
            "data": None,
        }

    try:
        SAPService.ensure_session()
    except Exception as e:
        return {
            "status": "failed",
            "message": f"Failed to initialize SAP session: {str(e)}",
            "data": None,
        }

    all_data = []
    skip = 0

    while True:
        url = (
            f"{SERVICE_LAYER_URL}/PurchaseDeliveryNotes?"
            f"$filter=CardCode eq '{vendor_code}' and DocumentStatus eq 'bost_Open'"
            f"&$select=DocEntry,DocNum,DocDate,TaxDate,CreationDate,UpdateDate,BPL_IDAssignedToInvoice,DocTotalFc,"
            f"CardCode,CardName,DocTotal,DocTotalSys,DocCurrency,VatSum,"
            f"AddressExtension,TaxExtension,DocumentLines"
            f"&$top={batch_size}&$skip={skip}"
        )
        
        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
            "Content-Type": "application/json",
        }

        attempt = 0
        while attempt < max_retries:
            try:
                resp = requests.get(url, headers=headers, verify=False, timeout=30)
                resp.raise_for_status()
                batch = resp.json().get("value", [])

                if not isinstance(batch, list):
                    return {
                        "status": "failed",
                        "message": "Unexpected response format from SAP Service Layer.",
                        "data": None,
                    }

                all_data.extend(batch)

                # If fewer records than batch_size returned, we've reached the end
                if len(batch) < batch_size:
                    return {
                        "status": "success",
                        "message": f"Fetched {len(all_data)} open GRNs for vendor {vendor_code}.",
                        "data": all_data,
                    }

                skip += batch_size
                break  # exit retry loop if successful

            except requests.exceptions.RequestException as e:
                attempt += 1
                if attempt >= max_retries:
                    return {
                        "status": "failed",
                        "message": f"Failed after {max_retries} attempts: {str(e)}",
                        "data": None,
                    }
                time.sleep(retry_delay)


def filter_grn_response(grn):
    """
    Trim down the GRN structure for invoice matching with default fallbacks using original SAP field names.
    Returns: dict {status, message, data}
    """
    try:
        filtered = {
            "DocEntry": grn.get("DocEntry", 0),
            "DocNum": grn.get("DocNum", 0),
            "DocDate": grn.get("DocDate", ""),
            "CardCode": grn.get("CardCode", ""),
            "CardName": grn.get("CardName", ""),
            "DocTotal": grn.get("DocTotal", 0.0),
            "DocCurrency": grn.get("DocCurrency", ""),
            "DocTotalFc": grn.get("DocTotalFc", 0.0),
            # "TaxDate": grn.get("TaxDate", ""),
            "VatSum": grn.get("VatSum", 0.0),
            # "DocTotalSys": grn.get("DocTotalSys", 0.0),
            "BPL_IDAssignedToInvoice": grn.get("BPL_IDAssignedToInvoice", None),
            "DocumentLines": [
                {
                    "LineNum": line.get("LineNum", None),
                    "ItemCode": line.get("ItemCode", ""),
                    "ItemDescription": line.get("ItemDescription", ""),
                    "Quantity": line.get("Quantity", 0),
                    "RemainingOpenQuantity": line.get("RemainingOpenQuantity", 0),
                    # "BaseType": line.get("BaseType", 0),
                    # "BaseEntry": line.get("BaseEntry", 0),
                    # "BaseLine": line.get("BaseLine", 0),
                    "UnitPrice": line.get("UnitPrice", 0.0),
                    "LineTotal": line.get("LineTotal", 0.0),
                    "TaxAmount": line.get("TaxAmount", 0.0),
                    # "VatGroup": line.get("VatGroup", ""),
                    # "WarehouseCode": line.get("WarehouseCode", ""),
                    "TaxTotal": line.get("TaxTotal", 0.0),
                    # "UoMCode": line.get("UoMCode", ""),
                    # "OriginalItem": line.get("OriginalItem", ""),
                    "Price": line.get("Price", 0.0),
                    "PriceAfterVAT": line.get("PriceAfterVAT", 0.0),
                    # "TaxPercentagePerRow": line.get("TaxPercentagePerRow", 0.0)
                }
                for line in grn.get("DocumentLines", [])
            ]
            if grn.get("DocumentLines")
            else [],
        }

        return {
            "status": "success",
            "message": "GRN filtered successfully.",
            "data": filtered,
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Error filtering GRN: {str(e)}",
            "data": None,
        }


