import boto3
import json
from typing import Dict, List, Any, Optional
import re
import io
from pdf2image import convert_from_path
from PIL import Image
from dotenv import load_dotenv
import os


load_dotenv()


class AWSTextractSAPExtractor:
    def __init__(self, region_name: str = None):
        """
        Initialize AWS Textract client.
        Will use credentials from .env if present.
        """
        self.region_name = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")

        self.textract = boto3.client(
            "textract",
            region_name=self.region_name,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )

    def extract_sap_data(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract SAP data from PDF file.
        Always returns dict with status, message, and data.
        """
        try:
            # Convert PDF to images
            images = self._convert_pdf_to_images(pdf_path)
            if not images:
                return {
                    "status": "failed",
                    "message": "PDF conversion failed - unable to convert PDF to images",
                    "data": None,
                }

            # Process with Textract
            document_response = self._process_images_for_document_analysis(images)
            expense_response = self._process_images_for_expense_analysis(images)

            # Extract and structure data
            raw_text = self._extract_text_blocks(document_response)

            data = {
                "sap_fields": self._extract_sap_specific_fields(raw_text),
                "expense_data": self._extract_expense_data(expense_response),
                "tables": self._extract_tables(document_response),
                "key_value_pairs": self._extract_key_value_pairs(document_response),
                "raw_text": raw_text,
                "metadata": {
                    "pages_processed": len(images),
                    "file_path": pdf_path,
                    "total_blocks": len(document_response.get("Blocks", [])),
                    "expense_documents": len(expense_response.get("ExpenseDocuments", [])),
                },
            }

            # Add confidence summary if available
            if data["expense_data"].get("confidence_scores"):
                confidence_scores = data["expense_data"]["confidence_scores"]
                if confidence_scores:
                    avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
                    data["confidence_summary"] = {
                        "average_confidence": round(avg_confidence, 2),
                        "field_count": len(confidence_scores),
                        "high_confidence_fields": {k: v for k, v in confidence_scores.items() if v > 90},
                        "low_confidence_fields": {k: v for k, v in confidence_scores.items() if v < 70},
                    }

            return {
                "status": "success",
                "message": "SAP data extracted successfully",
                "data": data,
            }

        except Exception as e:
            return {
                "status": "failed",
                "message": f"{type(e).__name__}: {str(e)}",
                "data": None,
            }

    def _convert_pdf_to_images(self, pdf_path: str):
        """Convert PDF pages to images for Textract processing"""
        try:
            images = convert_from_path(pdf_path, dpi=300, fmt="PNG")
            return images
        except Exception:
            return []

    def _image_to_bytes(self, image):
        """Convert PIL image to bytes for Textract"""
        img_byte_arr = io.BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(img_byte_arr, format="PNG", quality=95)
        return img_byte_arr.getvalue()

    def _process_images_for_document_analysis(self, images):
        """Process images for document analysis (forms and tables)"""
        combined_blocks = []

        for page_num, image in enumerate(images, 1):
            try:
                image_bytes = self._image_to_bytes(image)
                response = self.textract.analyze_document(
                    Document={"Bytes": image_bytes},
                    FeatureTypes=["FORMS", "TABLES"],
                )

                page_blocks = response.get("Blocks", [])
                for block in page_blocks:
                    block["PageNumber"] = page_num

                combined_blocks.extend(page_blocks)

            except Exception:
                continue

        return {"Blocks": combined_blocks}

    def _process_images_for_expense_analysis(self, images):
        """Process images for expense analysis (invoice-specific)"""
        combined_expense_docs = []

        for page_num, image in enumerate(images, 1):
            try:
                image_bytes = self._image_to_bytes(image)
                response = self.textract.analyze_expense(Document={"Bytes": image_bytes})

                expense_docs = response.get("ExpenseDocuments", [])
                for doc in expense_docs:
                    doc["PageNumber"] = page_num

                combined_expense_docs.extend(expense_docs)

            except Exception:
                continue

        return {"ExpenseDocuments": combined_expense_docs}

    def _extract_text_blocks(self, response: Dict[str, Any]) -> str:
        """Extract all text from Textract response"""
        text_blocks = []

        if "Blocks" in response:
            for block in response["Blocks"]:
                if block["BlockType"] == "LINE":
                    text_blocks.append(block["Text"])

        return "\n".join(text_blocks)

    def _extract_key_value_pairs(self, response: Dict[str, Any]) -> Dict[str, str]:
        """Extract key-value pairs from FORMS analysis"""
        key_value_pairs = {}

        if "Blocks" not in response:
            return key_value_pairs

        block_map = {block["Id"]: block for block in response["Blocks"]}

        for block in response["Blocks"]:
            if block["BlockType"] == "KEY_VALUE_SET":
                if "KEY" in block["EntityTypes"]:
                    key_text = self._get_relationship_text(block, block_map, "CHILD")

                    value_text = ""
                    if "Relationships" in block:
                        for relationship in block["Relationships"]:
                            if relationship["Type"] == "VALUE":
                                for value_id in relationship["Ids"]:
                                    if value_id in block_map:
                                        value_block = block_map[value_id]
                                        value_text = self._get_relationship_text(
                                            value_block, block_map, "CHILD"
                                        )

                    if key_text and value_text:
                        key_value_pairs[key_text.strip()] = value_text.strip()

        return key_value_pairs

    def _extract_tables(self, response: Dict[str, Any]) -> List[List[str]]:
        """Extract tables from Textract response"""
        tables = []

        if "Blocks" not in response:
            return tables

        block_map = {block["Id"]: block for block in response["Blocks"]}

        for block in response["Blocks"]:
            if block["BlockType"] == "TABLE":
                table = self._extract_table_data(block, block_map)
                if table:
                    tables.append(table)

        return tables

    def _extract_expense_data(self, expense_response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured data from AnalyzeExpense response"""
        extracted_data = {
            "vendor_name": "",
            "invoice_number": "",
            "invoice_date": "",
            "total_amount": "",
            "currency": "",
            "tax_amount": "",
            "line_items": [],
            "confidence_scores": {},
        }

        if "ExpenseDocuments" not in expense_response:
            return extracted_data

        for expense_doc in expense_response["ExpenseDocuments"]:
            if "SummaryFields" in expense_doc:
                for field in expense_doc["SummaryFields"]:
                    field_type = field["Type"]["Text"]
                    field_value = (
                        field["ValueDetection"]["Text"]
                        if "ValueDetection" in field
                        else ""
                    )
                    field_confidence = (
                        field["ValueDetection"]["Confidence"]
                        if "ValueDetection" in field
                        else 0
                    )

                    if field_type == "VENDOR_NAME":
                        extracted_data["vendor_name"] = field_value
                        extracted_data["confidence_scores"]["vendor_name"] = field_confidence
                    elif field_type == "INVOICE_RECEIPT_ID":
                        extracted_data["invoice_number"] = field_value
                        extracted_data["confidence_scores"]["invoice_number"] = field_confidence
                    elif field_type == "INVOICE_RECEIPT_DATE":
                        extracted_data["invoice_date"] = field_value
                        extracted_data["confidence_scores"]["invoice_date"] = field_confidence
                    elif field_type == "TOTAL":
                        extracted_data["total_amount"] = field_value
                        extracted_data["confidence_scores"]["total_amount"] = field_confidence
                    elif field_type == "TAX":
                        extracted_data["tax_amount"] = field_value
                        extracted_data["confidence_scores"]["tax_amount"] = field_confidence

            if "LineItemGroups" in expense_doc:
                for line_group in expense_doc["LineItemGroups"]:
                    if "LineItems" in line_group:
                        for line_item in line_group["LineItems"]:
                            item_data = {}
                            if "LineItemExpenseFields" in line_item:
                                for field in line_item["LineItemExpenseFields"]:
                                    field_type = field["Type"]["Text"]
                                    field_value = (
                                        field["ValueDetection"]["Text"]
                                        if "ValueDetection" in field
                                        else ""
                                    )

                                    if field_type == "ITEM":
                                        item_data["description"] = field_value
                                    elif field_type == "PRICE":
                                        item_data["unit_price"] = field_value
                                    elif field_type == "QUANTITY":
                                        item_data["quantity"] = field_value
                                    elif field_type == "UNIT_PRICE":
                                        item_data["unit_price"] = field_value

                            if item_data:
                                extracted_data["line_items"].append(item_data)

        return extracted_data

    def _extract_sap_specific_fields(self, text: str) -> Dict[str, str]:
        """Extract SAP-specific fields using enhanced regex patterns"""
        patterns = {
            "po_number": [
                r"P\.?O\.?\s*[:#]?\s*(\d+)",
                r"Purchase\s+Order\s*[:#]?\s*(\d+)",
                r"PO\s*[-:#]?\s*(\d+)",
                r"أمر\s*شراء\s*(\d+)",
            ],
            "grn_number": [
                r"Goods\s+Receipt\s+PO\s*[:#]?\s*(\d+)",
                r"GRN\s*[:#]?\s*(\d+)",
                r"Receipt\s*[:#]?\s*(\d+)",
                r"GRP\s*[:#]?\s*(\d+)",
            ],
            "invoice_number": [
                r"Invoice\s*[#:]?\s*([A-Z0-9-]+)",
                r"INV[-:]?([A-Z0-9]+)",
                r"فاتورة\s*([A-Z0-9-]+)",
            ],
            "vat_number": [
                r"VAT\s*[:#]?\s*([0-9]{10,})",
                r"Tax\s+Reg\.\s+No\.\s*[:#]?\s*([0-9]+)",
                r"TRN\s*[:#]?\s*([0-9]+)",
            ],
            "vendor_name": [
                r"(ELITE\s+INTERNATIONAL[^,\n]*)",
                r"(BRC\s+Industrial[^,\n]*)",
                r"(JOTUN[^,\n]*)",
                r"(ZAMIL[^,\n]*)",
                r"(NOFA\s+UNITED[^,\n]*)",
                r"Supplier[:#]?\s*([A-Z][A-Za-z\s&]+?)(?:\n|,|$)",
            ],
            "vendor_code": [
                r"Supplier\s*[:#]?\s*([A-Z0-9]+)",
                r"Vendor\s*[:#]?\s*([A-Z0-9]+)",
                r"Code\s*[:#]?\s*([A-Z0-9]+)",
            ],
            "amount_sar": [
                r"SAR\s*([\d,]+\.?\d*)",
                r"Total[^0-9]*SAR\s*([\d,]+\.?\d*)",
                r"([\d,]+\.?\d*)\s*SAR",
                r"ريال\s*([\d,]+\.?\d*)",
            ],
            "date": [
                r"(\d{2}[/-]\d{2}[/-]\d{4})",
                r"(\d{4}[/-]\d{2}[/-]\d{2})",
                r"Date\s*[:#]?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
            ],
        }

        extracted_fields = {}

        for field_name, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    extracted_fields[field_name] = match.group(1).strip()
                    break

        return extracted_fields

    def _get_relationship_text(self, block, block_map, relationship_type):
        """Helper method to get text from related blocks"""
        text = ""
        if "Relationships" in block:
            for relationship in block["Relationships"]:
                if relationship["Type"] == relationship_type:
                    for child_id in relationship["Ids"]:
                        if child_id in block_map:
                            child_block = block_map[child_id]
                            if child_block["BlockType"] == "WORD":
                                text += child_block["Text"] + " "
        return text.strip()

    def _extract_table_data(self, table_block, block_map):
        """Helper method to extract table data"""
        table = []

        if "Relationships" not in table_block:
            return table

        cells = {}
        for relationship in table_block["Relationships"]:
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    if child_id in block_map:
                        cell_block = block_map[child_id]
                        if cell_block["BlockType"] == "CELL":
                            row_index = cell_block["RowIndex"] - 1
                            col_index = cell_block["ColumnIndex"] - 1
                            cell_text = self._get_relationship_text(
                                cell_block, block_map, "CHILD"
                            )

                            if row_index not in cells:
                                cells[row_index] = {}
                            cells[row_index][col_index] = cell_text

        if cells:
            max_row = max(cells.keys())
            for row_idx in range(max_row + 1):
                row_data = []
                if row_idx in cells:
                    max_col = max(cells[row_idx].keys()) if cells[row_idx] else 0
                    for col_idx in range(max_col + 1):
                        cell_value = cells[row_idx].get(col_idx, "")
                        row_data.append(cell_value)
                table.append(row_data)

        return table
