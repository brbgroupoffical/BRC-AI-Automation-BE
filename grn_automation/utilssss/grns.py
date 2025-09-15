import os, requests
from sap_integration.sap_service import SAPService

SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def fetch_grns_for_vendor(vendor_code):
    """
    Fetch open GRNs for a vendor.
    """
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
    return resp.json().get("value", [])


def filter_grn_response(grn):
    """Trim GRN structure for invoice matching."""
    return {
        "DocEntry": grn.get("DocEntry", 0),
        "DocNum": grn.get("DocNum", 0),
        "DocDate": grn.get("DocDate", ""),
        "CardCode": grn.get("CardCode", ""),
        "CardName": grn.get("CardName", ""),
        "DocCurrency": grn.get("DocCurrency", ""),
        "DocTotal": grn.get("DocTotal", 0.0),
        "VatSum": grn.get("VatSum", 0.0),
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
            }
            for line in grn.get("DocumentLines", [])
        ],
    }
