import os
import time
import google.generativeai as genai
from pathlib import Path
import json
import re
import tempfile
from dotenv import load_dotenv
import base64

# Load environment variables from .env file
load_dotenv()

# Configuration - Load from environment variable
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables. Please set it in .env file")

MODEL_CLASSIFY = "gemini-2.5-pro"  # Using 2.5 Pro for 100% accuracy
MAX_RETRIES = 3
RETRY_BACKOFF = 3.0
MAX_OUTPUT_TOKENS = 8192  # Pro model supports much higher token limits

# Initialize Gemini
genai.configure(api_key=API_KEY)

# Safety settings - BLOCK_NONE for all categories (business documents are safe)
SAFETY_SETTINGS = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
    },
]

# Classification prompt - optimized for Gemini 2.5 Pro
CLASSIFICATION_PROMPT = """
You are an expert AP invoice classifier for a Saudi company (BRC Industrial). Analyze this PDF document and classify it into ONE of these 7 cases:

*CASE 1: One Invoice One GRN*
- Single GRN document (titled "Goods Receipt PO" or similar)
- Single Invoice document from supplier
- Single Purchase Order document
- All documents relate to same transaction (matching PO numbers, supplier, amounts)
- Example: GRN #15343 + Invoice INV-000233 + PO #3006 from Elite International

*CASE 2: One Invoice Multiple GRN*
- Single Invoice document 
- Invoice contains multiple GRN numbers in line items or material descriptions
- Look for patterns like "GRN 60133, GRN 61SM" or multiple GRN references in item descriptions
- Example: Al Ittefaq Steel invoice with multiple REBAR line items referencing different GRNs

*CASE 3: One GRN Multiple Invoices*
- Single GRN document (Goods Receipt PO)
- GRN references multiple invoice numbers in "Supplier Ref. No." field
- Pattern like "INV-42898 & 42899" or "Invoice 123, Invoice 124"
- Example: GRN #15259 referencing "INV-42898 & 42899" from National Bearing

*CASE 4: Invoice Not Matching GRN - Slightly Different*
- GRN and Invoice present for same supplier/transaction
- Same items but different quantities or amounts (variance typically <15%)
- Same invoice/GRN numbers but amounts don't match exactly
- Example: GRN shows SAR 29,040 but Invoice shows SAR 26,400 for same items

*CASE 5: Foreign Supplier Invoices (Imports) + Bayan Certificate*
- Foreign supplier (non-Saudi company address: Italy, China, Germany, USA, etc.)
- Currency other than SAR (EUR, USD, CNY, etc.)
- Contains "Bayan Certificate" or "Customs Declaration" document with Saudi customs stamps
- May include: Certificate of Origin, Bill of Lading, shipping documents, insurance certificates
- Example: OSCAM S.R.L. (Italy) invoice with Bayan certificate, EUR currency

*CASE 6: Landed Cost Invoice Booking*
- Multiple service provider invoices (not product invoices)
- All reference same Bill of Lading, Container number, or Job Order number
- Services like: customs clearance, freight charges, port charges, trucking, examination fees
- Cost allocation for import-related services from logistics companies
- Example: Excellence Logistics invoices for customs duty, port examination, trucking charges

*CASE 7: Services Invoices - No GRN Only GL*
- Service-based invoice (labor, consulting, maintenance, rent, manpower)
- NO "Goods Receipt PO" document present
- Time-based billing (hourly, daily, monthly rates)
- Service descriptions with staff count, hours, service periods
- No physical goods or inventory items
- Example: Mithaq Al Andalus manpower invoice for 12 staff, 2,629 hours

*CRITICAL ANALYSIS POINTS:*
1. Look for document titles and headers carefully
2. Identify if supplier is Saudi (Arabic company names, SAR currency) vs Foreign
3. Check for "Goods Receipt PO" vs "Invoice" vs "Service" document types
4. Note currency used (SAR indicates domestic, EUR/USD indicates import)
5. Look for customs documentation (Bayan certificates, customs stamps)
6. Count GRN and Invoice relationships (one-to-one vs one-to-many)
7. Distinguish between product purchases vs service billing

*RESPONSE FORMAT:*
Return ONLY a valid JSON object with this exact structure:
{
    "case_number": 1,
    "case_name": "One Invoice One GRN",
    "confidence": 0.95,
    "reasoning": "brief explanation of key factors that led to this classification",
    "key_documents_found": ["list of document types identified"],
    "supplier_name": "name of the supplier/vendor",
    "supplier_type": "Saudi or Foreign",
    "currency": "SAR/EUR/USD/CNY/etc",
    "grn_count": 1,
    "invoice_count": 1,
    "has_bayan_certificate": false,
    "service_based": false
}

Respond with ONLY the JSON object. No markdown, no extra text.
"""

def classify_pdf_case(pdf_binary, pdf_name):
    """
    Classify PDF using Gemini 2.5 Pro with inline content
    
    Args:
        pdf_binary (bytes): PDF file content as bytes
        pdf_name (str): Name of the PDF file
        
    Returns:
        dict: Classification result or None if failed
    """
    
    try:
        print(f"[INFO] Preparing {pdf_name} for Gemini classification...")
        
        # Initialize model with generation config and safety settings
        generation_config = {
            "temperature": 0.1,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        
        model = genai.GenerativeModel(
            MODEL_CLASSIFY,
            generation_config=generation_config,
            safety_settings=SAFETY_SETTINGS
        )
        
        # Create content parts - text prompt + PDF as inline data
        # Convert binary to base64 string for the API
        pdf_base64 = base64.b64encode(pdf_binary).decode('utf-8')
        
        content_parts = [
            CLASSIFICATION_PROMPT,
            {
                "mime_type": "application/pdf",
                "data": pdf_base64
            }
        ]
        
        print(f"[INFO] Sending to Gemini {MODEL_CLASSIFY}...")
        
        # Classify with retry logic
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[INFO] Classification attempt {attempt} for {pdf_name}")
                
                # Generate classification
                response = model.generate_content(
                    content_parts,
                    safety_settings=SAFETY_SETTINGS
                )
                
                # Check if response was blocked
                if not response or not hasattr(response, 'text'):
                    print(f"[ERROR] No valid response returned")
                    
                    # Check for safety blocking
                    if hasattr(response, 'prompt_feedback'):
                        feedback = response.prompt_feedback
                        print(f"[DEBUG] Prompt feedback: {feedback}")
                        
                        if hasattr(feedback, 'block_reason'):
                            print(f"[ERROR] Content blocked: {feedback.block_reason}")
                    
                    if hasattr(response, 'candidates') and response.candidates:
                        candidate = response.candidates[0]
                        finish_reason = candidate.finish_reason
                        print(f"[DEBUG] Finish reason: {finish_reason}")
                        
                        if hasattr(candidate, 'safety_ratings'):
                            print(f"[DEBUG] Safety ratings:")
                            for rating in candidate.safety_ratings:
                                print(f"  - {rating.category}: {rating.probability}")
                        
                        # Finish reason 2 = SAFETY block
                        if finish_reason == 2:
                            print(f"[ERROR] Response blocked by safety filters")
                            print(f"[INFO] This is a business invoice - not harmful content")
                            print(f"[INFO] This can be a random Gemini API issue. Retrying...")
                    
                    # Retry with longer backoff
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF * attempt * 2
                        print(f"[INFO] Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[ERROR] All attempts blocked by safety filters")
                        print(f"[INFO] Try uploading this PDF manually or contact support")
                        return None
                
                # Get response text
                try:
                    response_text = response.text
                except Exception as e:
                    print(f"[ERROR] Could not access response.text: {e}")
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF * attempt
                        print(f"[INFO] Retrying in {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    else:
                        return None
                
                if response_text:
                    print(f"[INFO] Received response from Gemini")
                    print(f"[DEBUG] Response length: {len(response_text)} characters")
                    
                    # Save response to file for debugging
                    try:
                        debug_file = f"gemini_response_{pdf_name.replace('.pdf', '').replace(' ', '_')[:30]}.txt"
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(response_text)
                        print(f"[DEBUG] Saved response to {debug_file}")
                    except Exception as e:
                        print(f"[DEBUG] Could not save response: {e}")
                    
                    result = parse_classification_response(response_text)
                    
                    if result:
                        print(f"[SUCCESS] Classified {pdf_name} as Case {result['case_number']}")
                        return result
                    else:
                        print(f"[WARN] Could not parse classification response for {pdf_name}")
                        if attempt < MAX_RETRIES:
                            print(f"[INFO] Will retry with fresh request...")
                        
                else:
                    print(f"[WARN] Empty response text from Gemini for {pdf_name}")
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[ERROR] Classification attempt {attempt} failed: {error_msg}")
                
                # Check for safety-related errors in exception
                if "finish_reason" in error_msg or "SAFETY" in error_msg.upper():
                    print(f"[ERROR] Safety filter triggered in exception")
                    print(f"[INFO] This is a business document, not harmful content")
                
                if attempt < MAX_RETRIES:
                    wait_time = RETRY_BACKOFF * attempt
                    print(f"[INFO] Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"[ERROR] All classification attempts failed for {pdf_name}")
        
        return None
        
    except Exception as e:
        print(f"[ERROR] PDF classification failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def parse_classification_response(response_text):
    """
    Parse Gemini response to extract classification JSON with robust error handling
    
    Args:
        response_text (str): Raw response from Gemini
        
    Returns:
        dict: Parsed classification result or None if parsing failed
    """
    try:
        # Clean up response text
        response_text = response_text.strip()
        
        # Remove markdown code blocks if present
        if "json" in response_text:
            parts = response_text.split("json")
            if len(parts) > 1:
                end_parts = parts[1].split("```")
                if len(end_parts) > 0:
                    response_text = end_parts[0].strip()
        elif "" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 3:
                response_text = parts[1].strip()
                if response_text.startswith(('json', 'JSON')):
                    response_text = response_text[4:].strip()
        
        # Check if response looks incomplete
        is_incomplete = False
        if response_text and not response_text.rstrip().endswith('}'):
            print(f"[WARN] Response appears incomplete")
            print(f"[DEBUG] Last 100 chars: ...{response_text[-100:]}")
            is_incomplete = True
            
            # Try to fix incomplete JSON
            if response_text.count('"') % 2 != 0:
                response_text = response_text + '"'
                print(f"[DEBUG] Closed open string")
            
            response_text = response_text.rstrip().rstrip(',')
            response_text = response_text + '}'
            print(f"[DEBUG] Added closing brace")
        
        # Try multiple JSON extraction methods
        classification_result = None
        
        # Method 1: Try direct JSON parse
        try:
            classification_result = json.loads(response_text)
            if is_incomplete:
                print(f"[SUCCESS] Successfully recovered incomplete JSON")
            else:
                print(f"[DEBUG] Successfully parsed JSON directly")
        except json.JSONDecodeError as e:
            print(f"[DEBUG] Direct JSON parse failed: {e}")
            
            # Method 2: Find JSON object with balanced braces
            brace_count = 0
            start_idx = -1
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        try:
                            potential_json = response_text[start_idx:i+1]
                            classification_result = json.loads(potential_json)
                            print(f"[DEBUG] Successfully parsed JSON with brace matching")
                            break
                        except json.JSONDecodeError:
                            start_idx = -1
                            continue
        
        if not classification_result:
            print(f"[ERROR] Could not extract valid JSON from response")
            print(f"[DEBUG] Response text (first 1000 chars):")
            print(response_text[:1000])
            return None
        
        # Validate required fields
        required_fields = ['case_number', 'case_name', 'confidence', 'reasoning']
        missing_fields = [field for field in required_fields if field not in classification_result]
        
        if missing_fields:
            print(f"[ERROR] Missing required fields: {missing_fields}")
            print(f"[DEBUG] Found fields: {list(classification_result.keys())}")
            
            # Try to fill in missing fields with defaults
            if 'case_number' not in classification_result:
                print(f"[ERROR] Cannot proceed without case_number")
                return None
            
            if 'case_name' not in classification_result:
                case_names = {
                    1: "One Invoice One GRN",
                    2: "One Invoice Multiple GRN",
                    3: "One GRN Multiple Invoices",
                    4: "Invoice Not Matching GRN",
                    5: "Foreign Supplier + Bayan Certificate",
                    6: "Landed Cost Invoice",
                    7: "Services Invoice"
                }
                classification_result['case_name'] = case_names.get(classification_result['case_number'], "Unknown")
                print(f"[WARN] Added missing case_name")
            
            if 'confidence' not in classification_result:
                classification_result['confidence'] = 0.9
                print(f"[WARN] Added default confidence")
            
            if 'reasoning' not in classification_result:
                classification_result['reasoning'] = "Classification based on document analysis"
                print(f"[WARN] Added default reasoning")
        
        # Validate case number
        case_number = classification_result.get('case_number')
        if not isinstance(case_number, int) or case_number < 1 or case_number > 7:
            print(f"[ERROR] Invalid case number: {case_number} (type: {type(case_number)})")
            return None
        
        # Validate confidence
        confidence = classification_result.get('confidence')
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            print(f"[WARN] Invalid confidence value: {confidence}, setting to 0.9")
            classification_result['confidence'] = 0.9
        
        return classification_result
        
    except Exception as e:
        print(f"[ERROR] Response parsing failed: {str(e)}")
        print(f"[DEBUG] Response text (first 500 chars): {response_text[:500] if response_text else 'None'}")
        import traceback
        traceback.print_exc()
        return None

def test_classification(pdf_file_path):
    """
    Test function to classify a local PDF file
    
    Args:
        pdf_file_path (str): Path to PDF file
        
    Returns:
        dict: Classification result
    """
    try:
        with open(pdf_file_path, 'rb') as f:
            pdf_binary = f.read()
        
        pdf_name = os.path.basename(pdf_file_path)
        result = classify_pdf_case(pdf_binary, pdf_name)
        
        if result:
            print(f"\n{'='*60}")
            print(f"CLASSIFICATION RESULT:")
            print(f"{'='*60}")
            print(f"Case: {result['case_number']} - {result['case_name']}")
            print(f"Confidence: {result['confidence']}")
            print(f"Reasoning: {result['reasoning']}")
            print(f"Supplier: {result.get('supplier_name', 'Unknown')}")
            print(f"Type: {result.get('supplier_type', 'Unknown')}")
            print(f"Currency: {result.get('currency', 'Unknown')}")
            print(f"{'='*60}")
        else:
            print("\n" + "="*60)
            print("CLASSIFICATION FAILED")
            print("="*60)
            print("Possible reasons:")
            print("1. PDF content triggered safety filters (random Gemini issue)")
            print("2. PDF is corrupted or unreadable")
            print("3. Network connectivity issues")
            print("Recommendation: Try again or use a different PDF")
            print("="*60)
            
        return result
        
    except Exception as e:
        print(f"Test failed: {str(e)}")
        return None

# Main function for testing
if __name__ == "__main__":
    print("="*60)
    print("GEMINI 2.5 PRO - INVOICE CLASSIFIER")
    print("="*60)
    print(f"Model: {MODEL_CLASSIFY}")
    print(f"Max Tokens: {MAX_OUTPUT_TOKENS}")
    print(f"Safety: BLOCK_NONE (all categories)")
    print("="*60 + "\n")
    
    # Test with a local PDF file
    test_pdf = input("Enter path to test PDF file: ")
    if os.path.exists(test_pdf):
        test_classification(test_pdf)
    else:
        print("File not found")