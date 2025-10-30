import json
import os
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from dotenv import load_dotenv
from .prompt import SYSTEM_PROMPT_FOR_EXTRACT_VENDOR_FIELDS,SINGLE_GRN_VALIDATION_PROMPT,MULTIPLE_GRN_VALIDATION_PROMPT  
from dotenv import load_dotenv
from google import genai


load_dotenv()


api_key = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=api_key)


# Pydantic Models
class ValidationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED" 
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class DocumentLine(BaseModel):
    """SAP B1 Document Line for AP Invoice - Updated Structure"""
    LineNum: int = Field(description="Line number from GRN DocumentLines")
    RemainingOpenQuantity: float = Field(description="Quantity to invoice (from invoice data)")


class APInvoicePayload(BaseModel):
    """SAP B1 Purchase Invoice API payload - Updated Structure"""
    CardCode: str = Field(description="Vendor code from GRN")
    DocEntry: int = Field(description="GRN DocEntry from SAP")
    DocDate: str = Field(description="Invoice date (YYYY-MM-DD format)")
    NumAtCard: Optional[str] = Field(default=None, description="Vendor reference number / Invoice number from vendor")
    BPL_IDAssignedToInvoice: int = Field(description="Branch ID from GRN")
    DocumentLines: List[DocumentLine] = Field(description="List of invoice line items")


class ValidationResult(BaseModel):
    """Single validation result for one invoice"""
    invoice_number: Optional[str] = Field(default=None, description="Invoice number from the vendor document")
    invoice_date: str = Field(description="The invoice date for this validation")
    status: ValidationStatus = Field(description="Validation status")
    reasoning: str = Field(description="Brief explanation (2-3 lines max)")
    payload: Optional[APInvoicePayload] = Field(default=None, description="SAP payload if successful")


class LineItem(BaseModel):
    """Individual line item from invoice"""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


class InvoiceWithLines(BaseModel):
    """Represents a single invoice with its date and line items"""
    invoice_number: Optional[str] = None
    invoice_date: str
    line_items: List[LineItem]


class VendorInfoWithScenario(BaseModel):
    """Vendor information with scenario detection and invoice dates"""
    vendor_code: Optional[str] = None
    vendor_name: Optional[str] = None
    grn_po_number: Optional[List[str]] = None
    scenario_detected: str
    invoices: Optional[List[InvoiceWithLines]] = None


class InvoiceProcessor:
    """
    Invoice Processing Methods for Backend Integration
    Provides three core methods: markdown extraction, vendor field extraction, and validation
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize processor with OpenAI API key
        
        Args:
            api_key: OpenAI API key (uses env var if not provided)
        """
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = OpenAI()
    
    # ============================================================================
    # METHOD 1: EXTRACT COMPLETE MARKDOWN
    # ============================================================================
    
    def extract_complete_markdown(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract complete data from PDF in markdown format using Gemini API
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            {
                "status": "success" | "error",
                "message": "Description of result",
                "data": "Complete markdown text" | None
            }
        """
        
        if not os.path.exists(pdf_path):
            return {
                "status": "error",
                "message": f"PDF file not found: {pdf_path}",
                "data": None
            }
        
        try:
            from google import genai
            from google.genai import types
            import pathlib
            
            # Initialize Gemini client
            api_key = os.getenv('GEMINI_API_KEY')
            gemini_client = genai.Client(api_key=api_key) 
            
            # Read PDF file
            filepath = pathlib.Path(pdf_path)
            
            # Prepare prompt
            prompt = (
                "Extract all text and data from this PDF document into clean markdown format. "
                "Preserve the complete structure, tables, headers, and all content exactly as it appears. "
                "Do not summarize, omit, or modify any information. "
                "Convert tables to markdown table format when possible. "
                "Maintain the original layout and hierarchy of information. "
                "Pay special attention to preserving ALL GRN numbers, invoice numbers, dates, and reference numbers."
            )
            
            # Generate content using Gemini
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(
                        data=filepath.read_bytes(),
                        mime_type='application/pdf',
                    ),
                    prompt
                ]
            )
            
            markdown_text = response.text
            
            return {
                "status": "success",
                "message": "PDF successfully extracted to markdown format using Gemini",
                "data": markdown_text
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to extract markdown from PDF: {str(e)}",
                "data": None
            }
        
    # ============================================================================
    # METHOD 2: EXTRACT VENDOR FIELDS
    # ============================================================================

    def extract_vendor_fields(self, markdown_text: str) -> Dict[str, Any]:
        """
        Extract vendor fields with scenario detection and invoice date mapping using Gemini
        
        Args:
            markdown_text: Complete markdown text from PDF
            
        Returns:
            {
                "status": "success" | "error",
                "message": "Description of result",
                "data": {
                    "vendor_info": {...},
                    "scenario_detected": "single_grn" | "multiple_grns",
                    "invoices": [...]
                }
            }
        """
        
        if not markdown_text or not isinstance(markdown_text, str):
            return {
                "status": "error",
                "message": "Invalid markdown text provided",
                "data": None
            }
        
        try:
            from google import genai
            from google.genai import types
            
            # Initialize Gemini client
            gemini_client = genai.Client()
            
            # Prepare content
            content = f"Analyze this document for scenario detection, extract vendor fields, and map invoice dates to line items:\n\n{markdown_text}"
            
            # Generate content with structured output using Pydantic schema
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_FOR_EXTRACT_VENDOR_FIELDS,
                    response_mime_type="application/json",
                    response_schema=VendorInfoWithScenario  # Use Pydantic model directly
                )
            )
            
            # Parse the JSON response and convert to Pydantic model
            result_dict = json.loads(response.text)
            vendor_info_obj = VendorInfoWithScenario(**result_dict)
            
            # Validate and process the result
            grn_count = len(vendor_info_obj.grn_po_number) if vendor_info_obj.grn_po_number else 0
            invoice_count = len(vendor_info_obj.invoices) if vendor_info_obj.invoices else 0
            
            if grn_count == 0:
                final_scenario = "no_grns_found"
                message = "No GRN numbers found in document"
                status = "error"
            elif grn_count == 1:
                final_scenario = "single_grn"
                message = f"Single GRN with {invoice_count} invoice(s)"
                status = "success"
            elif grn_count > 1:
                final_scenario = "multiple_grns"
                message = f"Multiple GRNs ({grn_count}) with {invoice_count} invoice(s)"
                status = "success"
            else:
                final_scenario = vendor_info_obj.scenario_detected
                message = "Document processed successfully"
                status = "success"
            
            return {
                "status": status,
                "message": message,
                "data": {
                    "vendor_info": {
                        "vendor_code": vendor_info_obj.vendor_code,
                        "vendor_name": vendor_info_obj.vendor_name,
                        "grn_po_number": vendor_info_obj.grn_po_number
                    },
                    "scenario_detected": final_scenario,
                    "invoices": [inv.dict() for inv in vendor_info_obj.invoices] if vendor_info_obj.invoices else []
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to extract vendor fields: {str(e)}",
                "data": None
            }
    
    # ============================================================================
    # METHOD 3: VALIDATE INVOICE
    # ============================================================================
    
    def validate_invoice(
        self,
        markdown_text: str,
        grn_data: Any,
        invoices: List[Dict[str, Any]],
        scenario: str
    ) -> Dict[str, Any]:
        """
        Validate invoice(s) against GRN data from SAP
        """
        
        try:
            if scenario == "single_grn":
                validation_results = self._validate_single_grn(markdown_text, grn_data, invoices)
            elif scenario == "multiple_grns":
                validation_results = self._validate_multiple_grns(markdown_text, grn_data, invoices)
            else:
                return {
                    "status": "error",
                    "message": f"Unknown scenario: {scenario}",
                    "data": None
                }
            
            # ============ NEW CODE (FIXED) ============
            
            # Build combined message from all reasoning
            message_parts = []
            overall_status = "success"
            
            # Build message and clean results
            cleaned_results = []
            
            for result in validation_results:
                invoice_number = result.get('invoice_number', 'Unknown')
                invoice_date = result.get('invoice_date', 'Unknown')
                status = result.get('status', 'UNKNOWN')
                reasoning = result.get('reasoning', 'No details provided')
                
                # Add to message with invoice number and date prefix
                message_parts.append(f"Invoice {invoice_number} ({invoice_date}): {reasoning}")
                
                # Determine overall status
                if status == "FAILED":
                    overall_status = "error"
                elif status == "REQUIRES_REVIEW":
                    if overall_status != "error":
                        overall_status = "warning"
                
                # Create cleaned result WITHOUT reasoning field
                cleaned_result = {
                    "invoice_number": invoice_number,
                    "invoice_date": invoice_date,
                    "status": status,
                    "payload": result.get('payload')
                }
                cleaned_results.append(cleaned_result)
            
            # Combine all messages - NO SUMMARY PREFIX
            # Just use the actual AI reasoning
            combined_message = " | ".join(message_parts)
            
            # ============ END NEW CODE ============
            
            return {
                "status": overall_status,
                "message": combined_message,  # Now contains only AI reasoning
                "data": {
                    "validation_results": cleaned_results
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Validation error: {str(e)}",
                "data": None
            }
    
    # ============================================================================
    # INTERNAL HELPER METHODS
    # ============================================================================
    
    def _validate_single_grn(
        self,
        markdown_text: str,
        grn_data: Dict[Any, Any],
        invoices: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate invoices against single GRN (internal method)"""
        
        validation_results = []
        
        for invoice in invoices:
            invoice_number = invoice.get('invoice_number', 'N/A')
            invoice_date = invoice.get('invoice_date', 'N/A')
            
            user_content = f"""
            Validate this specific invoice against the GRN data.

            ## INVOICE DATA:
            Invoice Number: {invoice_number}
            Invoice Date: {invoice_date}
            Line Items: {json.dumps(invoice['line_items'], indent=2)}

            ## COMPLETE MARKDOWN (for context):
            {markdown_text}

            ## GRN DATA FROM SAP:
```json
            {json.dumps(grn_data, indent=2)}
```

            ## VALIDATION REQUEST (SINGLE GRN):
            1. Validate invoice line items against GRN DocumentLines
            2. Ensure invoice quantities ≤ RemainingOpenQuantity for each line
            3. Validate amounts, descriptions, and prices
            4. If successful, construct SAP payload using:
               - CardCode from GRN
               - DocEntry from GRN
               - DocDate = {invoice_date}
               - NumAtCard = {invoice_number} (use exactly as provided)
               - BPL_IDAssignedToInvoice from GRN
               - DocumentLines with LineNum and RemainingOpenQuantity (invoice qty)
            """
            
            result = self._execute_validation(user_content, "SINGLE_GRN_VALIDATION_PROMPT")
            result["invoice_number"] = invoice_number
            result["invoice_date"] = invoice_date
            validation_results.append(result)
        
        return validation_results
    
    def _validate_multiple_grns(
        self,
        markdown_text: str,
        grn_data_list: List[Dict[Any, Any]],
        invoices: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate invoice against multiple GRNs (internal method)"""
        
        validation_results = []
        
        for invoice in invoices:
            invoice_number = invoice.get('invoice_number', 'N/A')
            invoice_date = invoice.get('invoice_date', 'N/A')
            
            user_content = f"""
            Validate this invoice against MULTIPLE GRNs.

            ## INVOICE DATA:
            Invoice Number: {invoice_number}
            Invoice Date: {invoice_date}
            Line Items: {json.dumps(invoice['line_items'], indent=2)}

            ## COMPLETE MARKDOWN (for context):
            {markdown_text}

            ## MULTIPLE GRN DATA FROM SAP:
```json
            {json.dumps(grn_data_list, indent=2)}
```

            ## VALIDATION REQUEST (MULTIPLE GRNs):
            1. Match invoice line items to appropriate GRN DocumentLines across ALL GRNs
            2. Ensure invoice quantities ≤ combined RemainingOpenQuantity
            3. Aggregate validation across multiple GRNs
            4. If successful, construct SAP payload(s) with proper mapping
            5. IMPORTANT: Include NumAtCard = {invoice_number} (use exactly as provided) in the payload
            """
            
            result = self._execute_validation(user_content, "MULTIPLE_GRN_VALIDATION_PROMPT")
            result["invoice_number"] = invoice_number
            result["invoice_date"] = invoice_date
            validation_results.append(result)
        
        return validation_results
    
    def _execute_validation(self, user_content: str, prompt_type: str) -> Dict[str, Any]:
        """Execute validation API call (internal method)"""
        
        try:
            # Backend should load the appropriate validation prompt
            system_prompt = prompt_type  # Placeholder
            
            response = self.client.responses.parse(
                model="gpt-5",
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                text_format=ValidationResult
            )
            
            validation_result = response.output_parsed
            
            return {
                "invoice_number": validation_result.invoice_number,
                "status": validation_result.status,
                "reasoning": validation_result.reasoning,
                "payload": validation_result.payload.dict() if validation_result.payload else None
            }

        except Exception as e:
            return {
                "invoice_number": None,
                "status": "FAILED",
                "reasoning": f"API Error: {str(e)}",
                "payload": None
            }