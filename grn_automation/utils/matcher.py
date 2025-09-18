def matching_grns(vendor_code, grn_po, grns):
    """
    Match the GRN using GRN PO number and return the matching payload with all GRNs.
    Uses existing DocumentLines from filtered GRNs (no redundant API call).
    Returns: dict {status, message, data}
    """
    try:
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
                    "TotalAmount": grn.get("DocTotal", 0.0),
                    "Tax": grn.get("VatSum", 0.0),
                    "DocumentLines": document_lines_payload,
                }
                break

        if matched_payload is None:
            return {
                "status": "failed",
                "message": f"No matching GRN found for PO number {grn_po} and vendor {vendor_code}.",
                "data": None,
            }

        return {
            "status": "success",
            "message": f"Matching GRN found for PO number {grn_po}.",
            "data": {
                "matched_payload": matched_payload,
            },
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Error while matching GRNs: {str(e)}",
            "data": None,
        }
