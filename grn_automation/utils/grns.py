import os
import requests
from sap_integration.sap_service import SAPService

SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def fetch_grns_for_vendor(vendor_code):
    """
    Fetch open GRNs for a vendor.
    Returns: dict {status, message, data}
    """
    try:
        SAPService.ensure_session()
        url = (
            f"{SERVICE_LAYER_URL}/PurchaseDeliveryNotes?"
            f"$filter=CardCode eq '{vendor_code}' and DocumentStatus eq 'bost_Open'"
            f"&$select=DocEntry,DocNum,DocDate,TaxDate,CreationDate,UpdateDate,"
            f"CardCode,CardName,DocTotal,DocTotalSys,DocCurrency,VatSum,"
            f"AddressExtension,TaxExtension,DocumentLines"
        )
        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
            "Content-Type": "application/json",
        }

        resp = requests.get(url, headers=headers, verify=False, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("value", [])

        return {
            "status": "success",
            "message": f"Fetched {len(data)} open GRNs for vendor {vendor_code}.",
            "data": data,
        }

    except requests.exceptions.RequestException as e:
        return {
            "status": "failed",
            "message": f"Failed to fetch GRNs for vendor {vendor_code}: {str(e)}",
            "data": None,
        }


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
            "TaxDate": grn.get("TaxDate", ""),
            "CreationDate": grn.get("CreationDate", ""),
            "UpdateDate": grn.get("UpdateDate", ""),
            "CardCode": grn.get("CardCode", ""),
            "CardName": grn.get("CardName", ""),
            "DocCurrency": grn.get("DocCurrency", ""),
            "DocTotal": grn.get("DocTotal", 0.0),
            "DocTotalSys": grn.get("DocTotalSys", 0.0),
            "VatSum": grn.get("VatSum", 0.0),
            "ShipToCity": grn.get("AddressExtension", {}).get("ShipToCity", ""),
            "ShipToCountry": grn.get("AddressExtension", {}).get("ShipToCountry", ""),
            "CountryS": grn.get("TaxExtension", {}).get("CountryS", ""),
            "DocumentLines": [
                {
                    "BaseType": line.get("BaseType", 0),
                    "BaseEntry": line.get("BaseEntry", 0),
                    "BaseLine": line.get("BaseLine", 0),
                    "ItemCode": line.get("ItemCode", ""),
                    "ItemDescription": line.get("ItemDescription", ""),
                    "Quantity": line.get("Quantity", 0),
                    "UnitPrice": line.get("UnitPrice", 0.0),
                    "LineTotal": line.get("LineTotal", 0.0),
                    "TaxAmount": line.get("TaxAmount", 0.0),
                    "VatGroup": line.get("VatGroup", ""),
                    "WarehouseCode": line.get("WarehouseCode", ""),
                    "UoMCode": line.get("UoMCode", ""),
                    "OriginalItem": line.get("OriginalItem", ""),
                    "PriceAfterVAT": line.get("PriceAfterVAT", 0.0),
                    "TaxPercentagePerRow": line.get("TaxPercentagePerRow", 0.0),
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
