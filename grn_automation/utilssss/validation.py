def create_ap_invoice(sap_payload):
    """
    Post validated invoice to SAP.
    """
    SAPService.ensure_session()
    base_url = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
    url = f"{base_url}/PurchaseInvoices"
    headers = {
        "Cookie": f"B1SESSION={SAPService.session_id}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json=sap_payload, verify=False, timeout=30)
    if resp.status_code != 201:
        raise RuntimeError(f"Invoice posting failed: {resp.text}")
    return resp.json()
