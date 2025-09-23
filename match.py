import logging
import requests
import urllib3
import os
import pprint

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Service Layer URL from env or fallback
SERVICE_LAYER_URL = "https://10.10.10.32:50000/b1s/v2/"


def login_to_sap(session, service_layer_url, username, password, company_db):
    """Login to SAP Service Layer"""
    payload = {
        "UserName": username,
        "Password": password,
        "CompanyDB": company_db
    }
    url = f"{service_layer_url}Login"

    logging.info("Attempting SAP Login")
    response = session.post(url, json=payload, verify=False)

    if response.status_code != 200:
        logging.error(f"SAP Login Failed [Status {response.status_code}]: {response.text}")
        return False

    logging.info(f"SAP Login Successful [Status {response.status_code}]")
    return True


def fetch_grns_for_vendor(session, vendor_code):
    """Fetch GRNs for a given vendor (open only)"""
    url = (
        f"{SERVICE_LAYER_URL}PurchaseDeliveryNotes?"
        f"$filter=CardCode eq '{vendor_code}' and DocumentStatus eq 'bost_Open'"
        f"&$select=DocEntry,DocNum,DocDate,TaxDate,CreationDate,UpdateDate,"
        f"CardCode,CardName,DocTotal,DocTotalSys,DocCurrency,VatSum,AddressExtension,TaxExtension,DocumentLines"
    )
    logging.info(f"Fetching GRNs for vendor {vendor_code}")
    response = session.get(url, verify=False)

    if response.status_code != 200:
        raise Exception("Failed to fetch GRNs: " + response.text)

    return response.json().get("value", [])


def filter_grn_response(grn):
    """Trim down the GRN structure for invoice matching with default fallbacks using original SAP field names"""
    return {
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
                "TaxPercentagePerRow": line.get("TaxPercentagePerRow", 0.0)
            }
            for line in grn.get("DocumentLines", [])
        ] if grn.get("DocumentLines") else []
    }


def matching_grns(vendor_code, grn_po, grns):
    """
    Match the GRN using GRN PO number and return the matching payload with all GRNs.
    Uses existing DocumentLines from filtered GRNs (no redundant API call).
    """
    matched_payloads = []
    grn_po_str = str(grn_po).strip() if grn_po else ""

    for grn in grns:
        current_po = str(grn.get("DocNum", "")).strip()
        if current_po == grn_po_str:
            doc_entry = grn.get("DocEntry", 0)

            document_lines_payload = [
                    {
                        "BaseType": line.get("BaseType", 0),# Based on your system
                        "BaseEntry": line.get("BaseEntry", 0),
                        "BaseLine": line.get("BaseLine", 0),
                        "Quantity": line.get("Quantity", 0),
                        "UnitPrice": line.get("UnitPrice", 0.0),
                        "ItemCode": line.get("ItemCode", ""),
                        "ItemDescription": line.get("ItemDescription", ""),
                        "LineTotal": line.get("LineTotal", 0.0),
                    }
                    for line in grn.get("DocumentLines", [])
                ]

            matched_payload = {
                "CardCode": vendor_code,
                "DocDate": grn.get("DocDate", ""),
                "Total Amount": grn.get("DocTotal", 0.0),
                "Tax": grn.get("VatSum", 0.0),
                "DocumentLines": document_lines_payload
            }
            matched_payloads.append({
                "vendor_code": vendor_code,
                "matched_payload": matched_payload
            }

            )

    return matched_payloads if matched_payloads else None



def logout_from_sap(session, service_layer_url):
    """Logout from SAP Service Layer"""
    url = f"{service_layer_url}Logout"
    logging.info("Attempting SAP Logout")
    response = session.post(url, verify=False)

    if response.status_code in (200, 204):
        logging.info(f"SAP Logout successful [Status {response.status_code}]")
    else:
        logging.error(f"SAP Logout failed [Status {response.status_code}]: {response.text}")



    # Credentials
    # username = "HOFT1"
    # password = "s@p9510"
    # company_db = "TEST"

def main():
    # Credentials
    # # SAP_SERVICE_LAYER_URL
    # SAP_SERVICE_LAYER_URL= "https://10.10.10.32:50000/b1s/v2"

    username = "HOFT1"
    password = "s@p9510"
    company_db = "TEST"

    vendor_code = "S00166"

    # Dummy PO list to match (in real scenario, this may come from invoice or another system)
    po_numbers_to_match = ["16064"]  

    logging.info("Starting SAP Connection Sequence")

    with requests.Session() as session:
        # Login
        if not login_to_sap(session, SERVICE_LAYER_URL, username, password, company_db):
            logging.error("Exiting due to login failure.")
            return

        # Fetch and filter GRNs
        grns = fetch_grns_for_vendor(session, vendor_code)
        filtered = [filter_grn_response(grn) for grn in grns]

        if filtered:
            logging.info(f"Fetched {len(filtered)} open GRNs for vendor {vendor_code}")
            for grn in filtered:
                logging.info(f"GRN DocNum: {grn['DocNum']} | Vendor: {grn['CardCode']} | Total: {grn['DocTotal']}")
        else:
            logging.info("No open GRNs found.")

        # 🔑 Match PO numbers against GRNs
        matched_results = []
        for po in po_numbers_to_match:
            matches = matching_grns(vendor_code, po, filtered)
            if matches:
                matched_results.extend(matches)

        # Log results
        if matched_results:
            logging.info(f"Found {len(matched_results)} matched GRNs for PO list {po_numbers_to_match}")
            for match in matched_results:
               # logging.info(f"complete matched payload:")
                pprint.pprint(match)
        else:
            logging.info(f"No GRNs matched for PO list {po_numbers_to_match}")

        # Logout
        logout_from_sap(session, SERVICE_LAYER_URL)

    logging.info("SAP connection sequence complete.")



if __name__ == "__main__":
    main()