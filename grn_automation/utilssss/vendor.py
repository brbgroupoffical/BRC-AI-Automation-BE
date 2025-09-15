import os, re, json
from sap_integration.sap_service import SAPService

SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def get_vendor_code_from_api(vendor_name):
    """
    Fetch vendor code from SAP B1 using the Service Layer.
    """
    SAPService.ensure_session()
    url = f"{SERVICE_LAYER_URL}/BusinessPartners"
    params = {
        "$filter": f"CardType eq 'cSupplier' and CardName eq '{vendor_name}'",
        "$select": "CardCode,CardName",
    }
    headers = {
        "Cookie": f"B1SESSION={SAPService.session_id}",
        "Content-Type": "application/json",
    }
    resp = requests.get(url, params=params, headers=headers, verify=False, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("value", [])
    return data[0]["CardCode"] if data else None


def get_vendor_code(grn_file_path):
    """
    Extract vendor code from GRN PDF or fallback to SAP query.
    """
    pdf_data = extract_pdf_data(grn_file_path)
    vendor_code = pdf_data.get("vendor_code")
    company_name = pdf_data.get("company_name")
    grn_po = pdf_data.get("goods_receipt_po_number")

    if vendor_code:
        return vendor_code, grn_po, pdf_data
    return get_vendor_code_from_api(company_name), grn_po, pdf_data
