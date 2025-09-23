def matching_grns(vendor_code, grn_po, grns):
    """
    Match the GRN using GRN PO number and return the matching payloads with all GRNs.
    Uses existing DocumentLines from filtered GRNs (no redundant API call).
    Returns: dict {status, message, data}
    """
    try:
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

                matched_payloads.append({
                    "CardCode": vendor_code,
                    "DocDate": grn.get("DocDate", ""),
                    "TotalAmount": grn.get("DocTotal", 0.0),
                    "Tax": grn.get("VatSum", 0.0),
                    "DocumentLines": document_lines_payload,
                })

        if not matched_payloads:
            return {
                "status": "failed",
                "message": f"No matching GRNs found for PO number {grn_po} and vendor {vendor_code}.",
                "data": None,
            }

        return {
            "status": "success",
            "message": f"{len(matched_payloads)} matching GRN(s) found for PO number {grn_po}.",
            "data": {
                "matched_payloads": matched_payloads,
            },
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": f"Error while matching GRNs: {str(e)}",
            "data": None,
        }
