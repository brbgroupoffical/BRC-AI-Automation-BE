def matching_grns(vendor_code, grn_po, grns):
    """
    Match the GRNs using provided GRN PO numbers and return the matching payloads.
    
    Args:
        vendor_code (str): Vendor code.
        grn_po (list[int] or int): One or multiple GRN PO numbers to match against DocNum.
        grns (list): List of GRN dicts (filtered GRNs).
    
    Returns:
        dict: {status, message, data}
    """
    try:
        # Normalize grn_po to a set of strings (to handle both int and list cases)
        if isinstance(grn_po, int):
            grn_po_set = {str(grn_po).strip()}
        elif isinstance(grn_po, list):
            grn_po_set = {str(po).strip() for po in grn_po if po is not None}
        else:
            return {
                "status": "failed",
                "message": "Invalid grn_po input, must be int or list of int.",
                "data": None,
            }

        matched_payloads = []

        for grn in grns:
            current_po = str(grn.get("DocNum", "")).strip()
            if current_po in grn_po_set:
                document_lines_payload = [
                    {
                        "LineNum": line.get("LineNum", None),
                        "ItemCode": line.get("ItemCode", ""),
                        "ItemDescription": line.get("ItemDescription", ""),
                        "Quantity": line.get("Quantity", 0),
                        "RemainingOpenQuantity": line.get("RemainingOpenQuantity", 0),
                        "UnitPrice": line.get("UnitPrice", 0.0),
                        "LineTotal": line.get("LineTotal", 0.0),
                    }
                    for line in grn.get("DocumentLines", [])
                ]

                matched_payloads.append({
                    "DocEntry": grn.get("DocEntry", 0),
                    "DocNum": grn.get("DocNum", 0),
                    "GRNDocDate": grn.get("DocDate", ""),
                    "CardCode": grn.get("CardCode", vendor_code), 
                    "CardName": grn.get("CardName", ""),
                    "DocTotal": grn.get("DocTotal", 0.0),
                    "DocCurrency": grn.get("DocCurrency", ""),
                    "DocTotalFc": grn.get("DocTotalFc", 0.0),
                    "Tax": grn.get("VatSum", 0.0),
                    "BPL_IDAssignedToInvoice": grn.get("BPL_IDAssignedToInvoice", None),
                    "DocumentLines": document_lines_payload,
                })

        if not matched_payloads:
            return {
                "status": "failed",
                "message": f"No matching GRNs found for PO numbers {list(grn_po_set)} and vendor {vendor_code}.",
                "data": None,
            }

        return {
            "status": "success",
            "message": f"{len(matched_payloads)} matching GRN(s) found for vendor {vendor_code}.",
            "data": matched_payloads,
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Error while matching GRNs: {str(e)}",
            "data": None,
        }
