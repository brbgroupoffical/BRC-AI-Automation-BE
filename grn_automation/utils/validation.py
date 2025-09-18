import json
from openai import OpenAI
from typing import Dict, Any
from .sap_invoice_models import ValidationResult
from .prompt import SYSTEM_PROMPT
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()



def validate_invoice_with_grn(invoice_data: Dict[Any, Any], grn_data: Dict[Any, Any]) -> ValidationResult:
    """
    Validates invoice data against GRN data using OpenAI responses.parse API
    
    Args:
        invoice_data: Extracted invoice data from PDF (JSON format)
        grn_data: GRN data retrieved from SAP B1 (JSON format)
    
    Returns:
        ValidationResult: Structured validation result with SAP payload or errors
    """
    
    # Prepare the user content with both datasets
    user_content = f"""
    Please validate the following invoice against the corresponding GRN data and provide a structured validation result.

    ## INVOICE DATA:
    ```json
    {json.dumps(invoice_data, indent=2)}
    ```

    ## GRN DATA FROM SAP:
    ```json
    {json.dumps(grn_data, indent=2)}
    ```

    ## VALIDATION REQUEST:
    1. Perform complete header and line-item validation
    2. Check all business rules and tolerance levels
    3. Calculate overall confidence score
    4. If validation succeeds, provide the SAP-ready AP Invoice payload
    5. If validation fails, provide detailed error explanations
    6. Include specific field-by-field comparison results in validation_details
    7. Recommend the appropriate next action

    Please ensure your response follows the exact ValidationResult schema structure.
    """

    try:
        # Call OpenAI API with structured output using responses.parse
        response = client.responses.parse(
            model="gpt-4.1",
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            text_format=ValidationResult
        )
        
        # Extract the parsed result and return immediately
        validation_result = response.output_parsed
        
        return {
            "status": validation_result.status,
            "reasoning": validation_result.reasoning,
            "payload": validation_result.payload.dict() if validation_result.payload else None
        }

    except Exception as e:
        # Handle any errors - return simple dict format
        return {
            "status": "FAILED",
            "reasoning": f"API Error occurred during validation: {str(e)}",
            "payload": None
        }

def process_invoice_validation(invoice_json: str, grn_json: str) -> Dict[str, Any]:
    """
    Complete validation workflow
    
    Args:
        invoice_json: JSON string of extracted invoice data
        grn_json: JSON string of GRN data from SAP
    
    Returns:
        Dict with validation results in clean format
    """
    
    try:
        # Parse JSON strings to dictionaries
        invoice_data = json.loads(invoice_json)
        grn_data = json.loads(grn_json)
        
        # Perform validation
        validation_result = validate_invoice_with_grn(invoice_data, grn_data)
        
        # Return simplified response format
        response = {
            "status": validation_result.status,
            "reasoning": validation_result.reasoning,
            "payload": validation_result.payload.model_dump() if validation_result.payload else None
        }
        
        return response
        
    except json.JSONDecodeError as e:
        return {
            "status": "FAILED",
            "reasoning": f"Invalid JSON format: {str(e)}",
            "payload": None
        }
    except Exception as e:
        return {
            "status": "FAILED", 
            "reasoning": f"Processing error: {str(e)}",
            "payload": None
        }