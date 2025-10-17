import os
import requests
import time
from sap_integration.sap_service import SAPService


SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


def fetch_purchase_invoice_by_docnum(doc_num, card_code=None, select_fields=None, max_retries=3, retry_delay=2):
    """
    Fetch a specific Purchase Invoice by DocNum and optionally CardCode from SAP Service Layer.

    Args:
        doc_num (str/int): The DocNum of the purchase invoice (e.g., 12342).
        card_code (str, optional): The vendor code (CardCode) for more accurate filtering.
        select_fields (str, optional): Comma-separated list of fields to select.
        max_retries (int): Number of retries for transient errors.
        retry_delay (int): Delay in seconds between retries.

    Returns:
        dict: {status (str), message (str), data (dict or None)}
    """
    if not doc_num:
        return {
            "status": "failed",
            "message": "Invalid doc_num provided.",
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

    # STEP 1: First, let's search by DocNum only to see if the invoice exists
    filter_query_docnum_only = f"DocNum eq {doc_num}"
    url_debug = f"{SERVICE_LAYER_URL}/PurchaseInvoices?$filter={filter_query_docnum_only}&$select=DocEntry,DocNum,CardCode,CardName&$top=5"
    
    headers = {
        "Cookie": f"B1SESSION={SAPService.session_id}",
        "Content-Type": "application/json",
    }

    try:
        print(f"\n[DEBUG STEP 1] Searching by DocNum only to see what exists...")
        print(f"[DEBUG] URL: {url_debug}")
        
        resp_debug = requests.get(url_debug, headers=headers, verify=False, timeout=30)
        resp_debug.raise_for_status()
        debug_data = resp_debug.json()
        
        debug_invoices = debug_data.get("value", [])
        print(f"[DEBUG] Found {len(debug_invoices)} invoice(s) with DocNum {doc_num}")
        
        if debug_invoices:
            print(f"[DEBUG] Available invoices with DocNum {doc_num}:")
            for inv in debug_invoices:
                print(f"  - DocEntry: {inv.get('DocEntry')}, DocNum: {inv.get('DocNum')}, CardCode: {inv.get('CardCode')}, CardName: {inv.get('CardName')}")
        else:
            print(f"[DEBUG] No invoices found with DocNum {doc_num} at all!")
            return {
                "status": "failed",
                "message": f"No Purchase Invoice found with DocNum {doc_num}. Please verify the DocNum exists in SAP.",
                "data": None,
            }
    except Exception as e:
        print(f"[DEBUG] Error during debug search: {str(e)}")
    
    # STEP 2: Now proceed with the actual search (with or without CardCode)
    if card_code:
        filter_query = f"DocNum eq {doc_num} and CardCode eq '{card_code}'"
    else:
        filter_query = f"DocNum eq {doc_num}"

    url = f"{SERVICE_LAYER_URL}/PurchaseInvoices?$filter={filter_query}"
    
    if select_fields:
        url += f"&$select={select_fields}"
    
    url += "&$top=1"

    attempt = 0
    while attempt < max_retries:
        try:
            print(f"\n[DEBUG STEP 2] Actual search with filters...")
            print(f"[DEBUG] URL: {url}")
            
            resp = requests.get(url, headers=headers, verify=False, timeout=30)
            print(f"[DEBUG] Response Status: {resp.status_code}")
            
            resp.raise_for_status()
            response_data = resp.json()

            if not isinstance(response_data, dict) or "value" not in response_data:
                print(f"[DEBUG] Unexpected response format: {response_data}")
                return {
                    "status": "failed",
                    "message": "Unexpected response format from SAP Service Layer.",
                    "data": None,
                }

            invoices = response_data.get("value", [])
            print(f"[DEBUG] Found {len(invoices)} invoice(s) matching filters")
            
            if not invoices or len(invoices) == 0:
                filter_desc = f"DocNum {doc_num}"
                if card_code:
                    filter_desc += f" and CardCode '{card_code}'"
                    suggestion = f" The invoice exists but with a different CardCode. Check the debug output above."
                else:
                    suggestion = ""
                    
                return {
                    "status": "failed",
                    "message": f"Purchase Invoice with {filter_desc} not found.{suggestion}",
                    "data": None,
                }

            print(f"[DEBUG] SUCCESS! Returning invoice data")
            return {
                "status": "success",
                "message": f"Successfully fetched Purchase Invoice with DocNum {doc_num}.",
                "data": invoices[0],
            }

        except requests.exceptions.HTTPError as e:
            error_detail = ""
            try:
                error_detail = e.response.json()
                print(f"[DEBUG] HTTP Error Detail: {error_detail}")
            except:
                error_detail = e.response.text
                print(f"[DEBUG] HTTP Error Text: {error_detail[:500]}")
            
            if e.response.status_code == 401:
                return {
                    "status": "failed",
                    "message": f"SAP session expired or invalid. Please re-authenticate.",
                    "data": None,
                }
            
            attempt += 1
            if attempt >= max_retries:
                return {
                    "status": "failed",
                    "message": f"Failed after {max_retries} attempts: {str(e)}. Detail: {error_detail}",
                    "data": None,
                }
            time.sleep(retry_delay)

        except requests.exceptions.RequestException as e:
            print(f"[DEBUG] Request Exception: {str(e)}")
            attempt += 1
            if attempt >= max_retries:
                return {
                    "status": "failed",
                    "message": f"Failed after {max_retries} attempts: {str(e)}",
                    "data": None,
                }
            time.sleep(retry_delay)
        
        except Exception as e:
            print(f"[DEBUG] Unexpected Exception: {str(e)}")
            return {
                "status": "failed",
                "message": f"Unexpected error: {str(e)}",
                "data": None,
            }

    return {
        "status": "failed",
        "message": "Max retries exceeded.",
        "data": None,
    }
