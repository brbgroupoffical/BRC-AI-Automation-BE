def matching_grns(vendor_code, grn_po, grns):
    """
    Match the GRN using GRN PO number and return the matching payload with all GRNs.
    Uses existing DocumentLines from filtered GRNs (no redundant API call).
    """
    matched_payload = None
    grn_po_str = str(grn_po).strip() if grn_po else ""

    for grn in grns:
        current_po = str(grn.get("DocNum", "")).strip()
        if current_po == grn_po_str:
            doc_entry = grn.get("DocEntry", 0)

            document_lines_payload = [
                {
                    "BaseType": 20,  # Based on your system
                    "BaseEntry": doc_entry,
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
            break

    if matched_payload is None:
        return None  # If no match is found, return None

    return {
        "vendor_code": vendor_code,
        "matched_payload": matched_payload
    }

