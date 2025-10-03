from openai import OpenAI
from pydantic import BaseModel
import json
import os
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

class VendorInfo(BaseModel):
    vendor_code: Optional[str] = None
    vendor_name: Optional[str] = None
    grn_po_number: Optional[str] = None

class PDFDataExtractor:
    def __init__(self, api_key: str):
        """
        Initialize the PDF Data Extractor with OpenAI API key
        
        Args:
            api_key: Your OpenAI API key
        """
        self.client = OpenAI(api_key=api_key)
    
    
    def extract_complete_markdown(self, pdf_path: str) -> dict:
        """
        Extract complete data from PDF in markdown format
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            dict: Response with status, message, and markdown data
        """
        
        # Verify file exists
        if not os.path.exists(pdf_path):
            return {
                "status": "error",
                "message": f"PDF file not found: {pdf_path}",
                "data": None
            }
        
        try:
            # Upload file to OpenAI
            with open(pdf_path, "rb") as pdf_file:
                file = self.client.files.create(
                    file=pdf_file,
                    purpose="assistants"
                )
            
            # Extract complete data in markdown format
            response = self.client.responses.create(
                model="gpt-4.1-mini",  # Use your original model
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text", 
                                "text": "Extract and return the full text from this PDF strictly verbatim, "
                         "exactly as it appears on every page. "
                         "Do not summarize, compress, interpret, describe, or generalize any part of the text. "
                         "Reproduce all repeated lines and details exactly as they appear, even if they look redundant. "
                         "Never replace content with phrases like 'continued', 'same format', 'etc.', or summaries. "
                         "Return the output in Markdown format only, with no introduction or conclusion text."
                            },
                            {"type": "input_file", "file_id": file.id}
                        ]
                    }
                ]
            )
            
            # Extract text content
            markdown_text = response.output[0].content[0].text
            
            # Clean up: delete uploaded file
            try:
                self.client.files.delete(file.id)
            except:
                pass  # Ignore cleanup errors
            
            return {
                "status": "success",
                "message": "PDF successfully extracted to markdown format",
                "data": markdown_text
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to extract markdown from PDF: {str(e)}",
                "data": None
            }


    def extract_vendor_fields(self, markdown_text: str) -> dict:
        """
        Extract specific vendor fields from markdown text
        
        Args:
            markdown_text: Complete markdown text from PDF
            
        Returns:
            dict: Response with status, message, and vendor field data
        """
        
        if not markdown_text or not isinstance(markdown_text, str):
            return {
                "status": "error",
                "message": "Invalid markdown text provided",
                "data": None
            }
        
        try:
            # Extract specific fields using structured output
            parse_response = self.client.responses.parse(
                model="gpt-4.1",  # Use your original model
                input=[
                    {
                        "role": "system", 
                        "content": "You are an expert at extracting vendor information from business documents. "
                                  "Analyze the provided document text and extract the following fields:\n"
                                  "- vendor_code: The supplier/vendor ID or code (usually alphanumeric like 'S00274', 'V001', etc.)\n"
                                  "- vendor_name: The full business name of the vendor/supplier company\n"
                                  "- grn_po_number: The GRN/PO number which is primarily labeled as 'Goods Receipt PO', 'Good Receipt PO', or 'GRPO'. "
                                  "If not found, look for secondary references as 'Ref.', 'Ref', 'Reference', or similar.\n\n"
                                  "Look for variations in field names and formats. If a field is not found, return null for that field."
                    },
                    {
                        "role": "user",
                        "content": f"Extract vendor_code, vendor_name, and grn_po_number from this document:\n\n{markdown_text}"
                    }
                ],
                text_format=VendorInfo
            )
            
            # Extract parsed result
            vendor_info = parse_response.output_parsed
            
            return {
                "status": "success",
                "message": "Vendor fields successfully extracted from markdown",
                "data": {
                    "vendor_code": vendor_info.vendor_code,
                    "vendor_name": vendor_info.vendor_name,
                    "grn_po_number": vendor_info.grn_po_number
                }
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to extract vendor fields: {str(e)}",
                "data": None
            }

# # Example usage and helper functions
# def save_markdown_to_file(markdown_text: str, output_path: str):
#     """Helper function to save markdown to file"""
#     with open(output_path, "w", encoding="utf-8") as f:
#         f.write(markdown_text)

# def save_vendor_info_to_file(vendor_info: dict, output_path: str):
#     """Helper function to save vendor info to JSON file"""
#     with open(output_path, "w", encoding="utf-8") as f:
#         json.dump(vendor_info, f, indent=4, ensure_ascii=False)

# # Usage example
# if __name__ == "__main__":
#     # Initialize extractor with environment variable
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise ValueError("Please set OPENAI_API_KEY environment variable")
    
#     extractor = PDFDataExtractor(api_key)
    
#     # Example usage
#     try:
#         pdf_file = "GRP3075-16064.pdf"
        
#         # Step 1: Extract complete markdown
#         print("Extracting complete document data...")
#         result1 = extractor.extract_complete_markdown(pdf_file)
        
#         if result1["status"] == "success":
#             markdown_data = result1["data"]
#             print(f"✅ {result1['message']}")
            
#             # Save markdown data (optional)
#             save_markdown_to_file(markdown_data, "extracted_data.md")
            
#             # Step 2: Extract vendor fields
#             print("Extracting vendor fields...")
#             result2 = extractor.extract_vendor_fields(markdown_data)
            
#             if result2["status"] == "success":
#                 vendor_fields = result2["data"]
#                 print(f"✅ {result2['message']}")
                
#                 # Save vendor fields (optional)
#                 save_vendor_info_to_file(vendor_fields, "vendor_info.json")
                
#                 # Display results
#                 print("\n=== EXTRACTION RESULTS ===")
#                 print(f"Vendor Code: {vendor_fields['vendor_code']}")
#                 print(f"Vendor Name: {vendor_fields['vendor_name']}")
#                 print(f"PO Number: {vendor_fields['grn_po_number']}")
#             else:
#                 print(f"❌ {result2['message']}")
#         else:
#             print(f"❌ {result1['message']}")
            
#     except Exception as e:
#         print(f"Error: {e}")