import logging
import requests
import os
from typing import Dict, List, Union, Any
from sap_integration.sap_service import SAPService
from datetime import datetime

logger = logging.getLogger(__name__)
SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")


class InvoiceCreationError(Exception):
    """Custom exception for invoice creation errors"""
    pass


def validate_grn_structure(grns: Union[Dict, List[Dict]]) -> List[Dict]:
    """
    Validate and normalize GRN input structure.
    
    Args:
        grns: Single GRN dict or list of GRN dicts
        
    Returns:
        List of validated GRN dictionaries
        
    Raises:
        InvoiceCreationError: If validation fails
    """
    # Normalize to list
    if isinstance(grns, dict):
        grns = [grns]
    
    if not grns or not isinstance(grns, list):
        raise InvoiceCreationError("No valid GRN data provided")
    
    # Validate required fields
    for idx, grn in enumerate(grns):
        if not isinstance(grn, dict):
            raise InvoiceCreationError(f"GRN at index {idx} is not a dictionary")
        
        required_fields = ["CardCode", "DocEntry"]
        missing_fields = [field for field in required_fields if not grn.get(field)]
        
        if missing_fields:
            raise InvoiceCreationError(
                f"GRN at index {idx} missing required fields: {', '.join(missing_fields)}"
            )
    
    return grns


def validate_vendor_consistency(grns: List[Dict]) -> str:
    """
    Ensure all GRNs belong to the same vendor.
    
    Args:
        grns: List of GRN dictionaries
        
    Returns:
        CardCode of the vendor
        
    Raises:
        InvoiceCreationError: If multiple vendors found
    """
    card_codes = {grn.get("CardCode") for grn in grns}
    
    if len(card_codes) > 1:
        raise InvoiceCreationError(
            f"Multiple vendors found: {', '.join(card_codes)}. "
            "Cannot create single invoice for multiple vendors."
        )
    
    return card_codes.pop()


def extract_document_lines(grns: List[Dict]) -> List[Dict]:
    """
    Extract and build document lines from GRNs with remaining quantities.
    
    Args:
        grns: List of GRN dictionaries
        
    Returns:
        List of document line dictionaries ready for SAP
    """
    doc_lines = []
    
    for grn in grns:
        doc_entry = grn.get("DocEntry")
        
        if not doc_entry:
            logger.warning(f"GRN missing DocEntry, skipping: {grn}")
            continue
        
        lines = grn.get("DocumentLines", [])
        
        if not lines:
            logger.warning(f"GRN {doc_entry} has no DocumentLines")
            continue
        
        for line in lines:
            # Priority: RemainingOpenQuantity > OpenQuantity > Quantity
            remaining_qty = (
                line.get("RemainingOpenQuantity") or
                line.get("OpenQuantity") or
                line.get("Quantity") or
                0
            )
            
            # Skip lines with no remaining quantity
            if remaining_qty <= 0:
                logger.debug(
                    f"Skipping line {line.get('LineNum')} in GRN {doc_entry}: "
                    f"No remaining quantity"
                )
                continue
            
            line_num = line.get("LineNum")
            if line_num is None:
                logger.warning(
                    f"Line in GRN {doc_entry} missing LineNum, skipping"
                )
                continue
            
            doc_lines.append({
                "BaseType": 20,              # GRPO base type
                "BaseEntry": doc_entry,       # GRPO DocEntry
                "BaseLine": line_num,         # GRPO line number
                "Quantity": remaining_qty     # Invoice quantity
            })
    
    return doc_lines


def build_invoice_payload(
    grns: List[Dict],
    doc_lines: List[Dict]
) -> Dict[str, Any]:
    """
    Build the complete invoice payload for SAP.
    
    Args:
        grns: List of GRN dictionaries
        doc_lines: List of document lines
        
    Returns:
        Complete invoice payload dictionary
    """
    # Use first GRN as base for header data
    base_grn = grns[0]
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    payload = {
        "CardCode": base_grn.get("CardCode"),
        "BPL_IDAssignedToInvoice": base_grn.get("BPL_IDAssignedToInvoice"),
        "DocDate": base_grn.get("DocDate") or today,  # Document Date
        "TaxDate": today,                              # Posting Date
        "DocumentLines": doc_lines
    }
    
    # Add optional DocDueDate if provided in base GRN
    if base_grn.get("DocDueDate"):
        payload["DocDueDate"] = base_grn["DocDueDate"]
    
    return payload


def create_dummy_response(
    payload: Dict[str, Any],
    doc_lines: List[Dict]
) -> Dict[str, Any]:
    """
    Generate dummy response for testing purposes.
    
    Args:
        payload: Invoice payload
        doc_lines: Document lines
        
    Returns:
        Dummy success response
    """
    return {
        "status": "success",
        "message": "Invoice created successfully (dummy mode)",
        "data": {
            "DocEntry": 99999,
            "CardCode": payload["CardCode"],
            "DocDate": payload["DocDate"],
            "BPL_IDAssignedToInvoice": payload.get("BPL_IDAssignedToInvoice"),
            "LinesCount": len(doc_lines),
            "TotalAmount": sum(
                line.get("Quantity", 0) for line in doc_lines
            ),
            "Lines": doc_lines,
        },
    }


def call_sap_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make the actual SAP Service Layer API call.
    
    Args:
        payload: Complete invoice payload
        
    Returns:
        API response dictionary
        
    Raises:
        InvoiceCreationError: If API call fails
    """
    if not SAPService.session_id:
        raise InvoiceCreationError("SAP session not initialized")
    
    headers = {
        "Cookie": f"B1SESSION={SAPService.session_id}",
        "Content-Type": "application/json",
    }
    
    url = f"{SERVICE_LAYER_URL}/PurchaseInvoices"
    
    try:
        logger.info(f"Creating invoice in SAP for vendor {payload['CardCode']}")
        logger.debug(f"Invoice payload: {payload}")
        
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=30
        )
        
        # Check for HTTP errors
        resp.raise_for_status()
        
        response_data = resp.json()
        logger.info(
            f"Invoice created successfully. DocEntry: {response_data.get('DocEntry')}"
        )
        
        return {
            "status": "success",
            "message": "Invoice created successfully",
            "data": response_data,
        }
    
    except requests.exceptions.Timeout:
        logger.error("SAP API request timed out", exc_info=True)
        raise InvoiceCreationError("SAP API request timed out after 30 seconds")
    
    except requests.exceptions.HTTPError as http_err:
        error_text = resp.text if resp is not None else str(http_err)
        logger.error(f"SAP API HTTP error: {error_text}", exc_info=True)
        
        # Try to extract SAP error message
        try:
            error_json = resp.json()
            error_msg = error_json.get("error", {}).get("message", {}).get("value", error_text)
        except:
            error_msg = error_text
        
        raise InvoiceCreationError(f"SAP API Error: {error_msg}")
    
    except requests.exceptions.RequestException as req_err:
        logger.error(f"SAP API request failed: {req_err}", exc_info=True)
        raise InvoiceCreationError(f"SAP API request failed: {str(req_err)}")
    
    except ValueError as json_err:
        logger.error(f"Failed to parse SAP API response: {json_err}", exc_info=True)
        raise InvoiceCreationError("Invalid JSON response from SAP API")


def create_invoice(
    grns: Union[Dict, List[Dict]],
    use_dummy: bool = True
) -> Dict[str, Any]:
    """
    Create A/P Invoice in SAP B1 from one or more GRPOs.
    
    Supports three scenarios:
    1. One GRN to One Invoice (1:1)
    2. One GRN to Multiple Invoices (1:many) - handled by calling this function multiple times
    3. Multiple GRNs to One Invoice (many:1)
    
    Args:
        grns: Single GRN dict or list of GRN dicts from validation payload
        use_dummy: If True, returns dummy response without calling SAP API
        
    Returns:
        dict with keys:
            - status: "success" or "failed"
            - message: Description of result
            - data: Invoice data or None on failure
            
    Example GRN structure:
        {
            "CardCode": "S00536",
            "DocEntry": 20170,
            "DocDate": "2025-09-07",
            "BPL_IDAssignedToInvoice": 3,
            "DocumentLines": [
                {
                    "LineNum": 0,
                    "RemainingOpenQuantity": 29.11
                }
            ]
        }
    """
    try:
        # Ensure SAP session is active (only for non-dummy mode)
        if not use_dummy:
            SAPService.ensure_session()
        
        # Step 1: Validate and normalize input
        try:
            validated_grns = validate_grn_structure(grns)
        except InvoiceCreationError as e:
            logger.error(f"GRN validation failed: {e}")
            return {
                "status": "failed",
                "message": str(e),
                "data": None,
            }
        
        # Step 2: Validate vendor consistency
        try:
            card_code = validate_vendor_consistency(validated_grns)
            logger.info(f"Processing invoice for vendor: {card_code}")
        except InvoiceCreationError as e:
            logger.error(f"Vendor validation failed: {e}")
            return {
                "status": "failed",
                "message": str(e),
                "data": None,
            }
        
        # Step 3: Extract document lines with remaining quantities
        doc_lines = extract_document_lines(validated_grns)
        
        if not doc_lines:
            logger.warning("No lines with remaining open quantity found")
            return {
                "status": "failed",
                "message": (
                    "All GRPO lines are fully invoiced or have no remaining "
                    "open quantity. No invoice created."
                ),
                "data": None,
            }
        
        logger.info(
            f"Prepared {len(doc_lines)} invoice line(s) from "
            f"{len(validated_grns)} GRN(s)"
        )
        
        # Step 4: Build invoice payload
        payload = build_invoice_payload(validated_grns, doc_lines)
        
        # Step 5: Return dummy response or call SAP API
        if use_dummy:
            logger.info("Dummy mode enabled, returning mock response")
            return create_dummy_response(payload, doc_lines)
        
        # Real SAP API call
        try:
            return call_sap_api(payload)
        except InvoiceCreationError as e:
            return {
                "status": "failed",
                "message": str(e),
                "data": None,
            }
    
    except Exception as e:
        logger.error(f"Unexpected error in create_invoice: {e}", exc_info=True)
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(e)}",
            "data": None,
        }