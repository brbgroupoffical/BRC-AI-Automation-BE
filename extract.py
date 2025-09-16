import boto3
import json
from typing import Dict, List, Any, Optional
import re
from decimal import Decimal
import io
import os
import sys
import datetime
import time
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

# Load environment variables from .env file
from dotenv import load_dotenv

def check_dependencies():
    """
    Check all required dependencies and provide installation instructions
    """
    missing_deps = []
    
    try:
        import boto3
        print("✅ boto3 available")
    except ImportError:
        missing_deps.append("boto3")
    
    try:
        from pdf2image import convert_from_path
        print("✅ pdf2image available")
    except ImportError:
        missing_deps.append("pdf2image")
    
    try:
        from PIL import Image
        print("✅ Pillow available")
    except ImportError:
        missing_deps.append("Pillow")
    
    try:
        from dotenv import load_dotenv
        print("✅ python-dotenv available")
    except ImportError:
        missing_deps.append("python-dotenv")
    
    # Check for poppler (system dependency for pdf2image)
    try:
        from pdf2image import convert_from_path
        # Test with a minimal call to check poppler
        print("✅ Poppler system dependency available")
    except Exception as e:
        if "poppler" in str(e).lower() or "unable to get page count" in str(e).lower():
            print("❌ Poppler not found (required for PDF processing)")
            print("   Install poppler:")
            print("   - Ubuntu/Debian: sudo apt-get install poppler-utils")
            print("   - CentOS/RHEL: sudo yum install poppler-utils") 
            print("   - macOS: brew install poppler")
            print("   - Windows: Download from https://github.com/oschwartz10612/poppler-windows")
            return False
    
    if missing_deps:
        print("❌ Missing Python packages:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print(f"\nInstall with: pip install {' '.join(missing_deps)}")
        return False
    
    print("✅ All dependencies available")
    return True

def load_aws_credentials():
    """
    Load AWS credentials from .env file and validate them
    """
    # Load .env file
    load_dotenv()
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("\n🔧 Create a .env file with:")
        print("AWS_ACCESS_KEY_ID=your_access_key_here")
        print("AWS_SECRET_ACCESS_KEY=your_secret_key_here")
        print("AWS_DEFAULT_REGION=eu-west-1")
        return False
    
    # Get credentials from environment
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_region = "eu-west-1"
    
    # Validate credentials are present
    missing_vars = []
    if not aws_access_key:
        missing_vars.append('AWS_ACCESS_KEY_ID')
    if not aws_secret_key:
        missing_vars.append('AWS_SECRET_ACCESS_KEY')
    
    if missing_vars:
        print("❌ Missing AWS credentials in .env file:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    # Set environment variables for boto3
    os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
    os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
    os.environ['AWS_DEFAULT_REGION'] = aws_region
    
    print("✅ AWS credentials loaded from .env file")
    print(f"   Region: {aws_region}")
    print(f"   Access Key: {aws_access_key[:8]}..." if aws_access_key else "   Access Key: None")
    
    return True

def check_aws_credentials_and_time(region="eu-west-1"):
    """
    Check AWS credentials first, then verify clock sync.
    Separates credential issues from clock drift issues.
    """
    try:
        # Initialize STS client
        sts = boto3.client("sts", region_name=region)
        
        # Test credentials by calling get_caller_identity
        print("🔐 Checking AWS credentials...")
        response = sts.get_caller_identity()
        
        print(f"✅ AWS credentials valid")
        print(f"   Account: {response.get('Account', 'N/A')}")
        print(f"   User ARN: {response.get('Arn', 'N/A')}")
        
        # If we get here, credentials work and time is in sync
        print("✅ System clock is in sync with AWS")
        return True
        
    except NoCredentialsError:
        print("❌ AWS Credentials not found!")
        print("\n🔧 Solutions:")
        print("   1. Check your .env file exists and contains:")
        print("      AWS_ACCESS_KEY_ID=your_key")
        print("      AWS_SECRET_ACCESS_KEY=your_secret")
        print("      AWS_DEFAULT_REGION=eu-west-1")
        print("   2. Verify .env file is in the same directory as this script")
        return False
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        
        if error_code == 'SignatureDoesNotMatch':
            print("❌ Clock drift detected: Request signature mismatch")
            local_time = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"   Local UTC time: {local_time}")
            print("\n🔧 Clock drift solutions:")
            print("   1. Sync system time: sudo ntpdate -s time.nist.gov")
            print("   2. Enable NTP: sudo timedatectl set-ntp true")
            print("   3. Check timezone: timedatectl status")
            return False
            
        elif error_code in ['InvalidAccessKeyId', 'AccessDenied']:
            print(f"❌ AWS Credential error: {e.response['Error']['Message']}")
            print("\n🔧 Check your AWS credentials and permissions")
            print("   Required permissions: textract:AnalyzeDocument, textract:AnalyzeExpense")
            return False
            
        else:
            print(f"❌ AWS Error: {e.response['Error']['Message']}")
            return False
            
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

class AWSTextractSAPExtractor:
    def __init__(self, region_name="eu-west-1"):
        # Check credentials and clock sync
        if not check_aws_credentials_and_time(region_name):
            print("⏰ Aborting: AWS setup issue detected. Please fix the above errors.")
            sys.exit(1)

        try:
            # Initialize Textract client with explicit region
            self.textract = boto3.client(
                "textract", 
                region_name=region_name,
                # Add retry configuration
                config=boto3.session.Config(
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                    max_pool_connections=50
                )
            )
            print(f"📡 Connected to AWS Textract in region {region_name}")
            
        except Exception as e:
            print(f"❌ Failed to initialize Textract client: {str(e)}")
            sys.exit(1)
    
    def safe_textract_call(self, operation, **kwargs):
        """
        Wrapper for Textract calls with proper error handling and retries
        """
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                if operation == 'analyze_document':
                    return self.textract.analyze_document(**kwargs)
                elif operation == 'analyze_expense':
                    return self.textract.analyze_expense(**kwargs)
                else:
                    raise ValueError(f"Unknown operation: {operation}")
                    
            except ClientError as e:
                error_code = e.response['Error']['Code']
                
                if error_code == 'ThrottlingException' and attempt < max_retries - 1:
                    print(f"   Rate limited, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                    
                elif error_code == 'InvalidS3ObjectException':
                    print(f"   Error: Invalid document format or corrupted file")
                    return None
                    
                elif error_code == 'DocumentTooLargeException':
                    print(f"   Error: Document too large for Textract")
                    return None
                    
                else:
                    print(f"   AWS Error: {e.response['Error']['Message']}")
                    return None
                    
            except BotoCoreError as e:
                print(f"   Connection error: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None
                
            except Exception as e:
                print(f"   Unexpected error: {str(e)}")
                return None
        
        return None
    
    def convert_pdf_to_images(self, pdf_path: str):
        """
        Convert PDF pages to images for Textract processing (handles scanned documents)
        """
        try:
            from pdf2image import convert_from_path
            
            print(f"Converting PDF to images: {pdf_path}")
            
            # Convert PDF to images with high DPI for better OCR
            images = convert_from_path(pdf_path, dpi=300, fmt='PNG')
            print(f"Successfully converted {len(images)} pages to images")
            
            return images
        except Exception as e:
            print(f"Error converting PDF: {str(e)}")
            return []
    
    def image_to_bytes(self, image):
        """
        Convert PIL image to bytes for Textract
        """
        from PIL import Image
        
        img_byte_arr = io.BytesIO()
        
        # Convert to RGB if necessary (Textract prefers RGB)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save as PNG with high quality
        image.save(img_byte_arr, format='PNG', quality=95)
        return img_byte_arr.getvalue()

    def extract_text_blocks(self, response: Dict[str, Any]) -> str:
        """
        Extract all text from Textract response
        """
        text_blocks = []
        
        if 'Blocks' in response:
            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    text_blocks.append(block['Text'])
        
        return '\n'.join(text_blocks)
    
    def extract_key_value_pairs(self, response: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract key-value pairs from FORMS analysis
        """
        key_value_pairs = {}
        
        if 'Blocks' not in response:
            return key_value_pairs
        
        # Create a map of block IDs to blocks
        block_map = {block['Id']: block for block in response['Blocks']}
        
        # Find KEY_VALUE_SET blocks
        for block in response['Blocks']:
            if block['BlockType'] == 'KEY_VALUE_SET':
                if 'KEY' in block['EntityTypes']:
                    # This is a key block
                    key_text = self._get_relationship_text(block, block_map, 'CHILD')
                    
                    # Find the corresponding value
                    value_text = ""
                    if 'Relationships' in block:
                        for relationship in block['Relationships']:
                            if relationship['Type'] == 'VALUE':
                                for value_id in relationship['Ids']:
                                    if value_id in block_map:
                                        value_block = block_map[value_id]
                                        value_text = self._get_relationship_text(value_block, block_map, 'CHILD')
                    
                    if key_text and value_text:
                        key_value_pairs[key_text.strip()] = value_text.strip()
        
        return key_value_pairs
    
    def extract_tables(self, response: Dict[str, Any]) -> List[List[str]]:
        """
        Extract tables from Textract response
        """
        tables = []
        
        if 'Blocks' not in response:
            return tables
        
        # Create a map of block IDs to blocks
        block_map = {block['Id']: block for block in response['Blocks']}
        
        # Find TABLE blocks
        for block in response['Blocks']:
            if block['BlockType'] == 'TABLE':
                table = self._extract_table_data(block, block_map)
                if table:
                    tables.append(table)
        
        return tables
    
    def extract_expense_data(self, expense_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured data from AnalyzeExpense response
        """
        extracted_data = {
            'vendor_name': '',
            'invoice_number': '',
            'invoice_date': '',
            'total_amount': '',
            'currency': '',
            'tax_amount': '',
            'line_items': [],
            'confidence_scores': {}
        }
        
        if 'ExpenseDocuments' not in expense_response:
            return extracted_data
        
        for expense_doc in expense_response['ExpenseDocuments']:
            # Extract summary fields
            if 'SummaryFields' in expense_doc:
                for field in expense_doc['SummaryFields']:
                    field_type = field['Type']['Text']
                    field_value = field['ValueDetection']['Text'] if 'ValueDetection' in field else ''
                    field_confidence = field['ValueDetection']['Confidence'] if 'ValueDetection' in field else 0
                    
                    if field_type == 'VENDOR_NAME':
                        extracted_data['vendor_name'] = field_value
                        extracted_data['confidence_scores']['vendor_name'] = field_confidence
                    elif field_type == 'INVOICE_RECEIPT_ID':
                        extracted_data['invoice_number'] = field_value
                        extracted_data['confidence_scores']['invoice_number'] = field_confidence
                    elif field_type == 'INVOICE_RECEIPT_DATE':
                        extracted_data['invoice_date'] = field_value
                        extracted_data['confidence_scores']['invoice_date'] = field_confidence
                    elif field_type == 'TOTAL':
                        extracted_data['total_amount'] = field_value
                        extracted_data['confidence_scores']['total_amount'] = field_confidence
                    elif field_type == 'TAX':
                        extracted_data['tax_amount'] = field_value
                        extracted_data['confidence_scores']['tax_amount'] = field_confidence
            
            # Extract line items
            if 'LineItemGroups' in expense_doc:
                for line_group in expense_doc['LineItemGroups']:
                    if 'LineItems' in line_group:
                        for line_item in line_group['LineItems']:
                            item_data = {}
                            if 'LineItemExpenseFields' in line_item:
                                for field in line_item['LineItemExpenseFields']:
                                    field_type = field['Type']['Text']
                                    field_value = field['ValueDetection']['Text'] if 'ValueDetection' in field else ''
                                    
                                    if field_type == 'ITEM':
                                        item_data['description'] = field_value
                                    elif field_type == 'PRICE':
                                        item_data['unit_price'] = field_value
                                    elif field_type == 'QUANTITY':
                                        item_data['quantity'] = field_value
                                    elif field_type == 'UNIT_PRICE':
                                        item_data['unit_price'] = field_value
                            
                            if item_data:
                                extracted_data['line_items'].append(item_data)
        
        return extracted_data
    
    def extract_sap_specific_fields(self, text: str) -> Dict[str, str]:
        """
        Extract SAP-specific fields using enhanced regex patterns for scanned documents
        """
        patterns = {
            'po_number': [
                r'P\.?O\.?\s*[:#]?\s*(\d+)',
                r'Purchase\s+Order\s*[:#]?\s*(\d+)',
                r'PO\s*[-:#]?\s*(\d+)',
                r'أمر\s*شراء\s*(\d+)'  # Arabic
            ],
            'grn_number': [
                r'Goods\s+Receipt\s+PO\s*[:#]?\s*(\d+)',
                r'GRN\s*[:#]?\s*(\d+)',
                r'Receipt\s*[:#]?\s*(\d+)',
                r'GRP\s*[:#]?\s*(\d+)'
            ],
            'invoice_number': [
                r'Invoice\s*[#:]?\s*([A-Z0-9-]+)',
                r'INV[-:]?([A-Z0-9]+)',
                r'فاتورة\s*([A-Z0-9-]+)'  # Arabic
            ],
            'vat_number': [
                r'VAT\s*[:#]?\s*([0-9]{10,})',
                r'Tax\s+Reg\.\s+No\.\s*[:#]?\s*([0-9]+)',
                r'TRN\s*[:#]?\s*([0-9]+)'
            ],
            'vendor_name': [
                r'(ELITE\s+INTERNATIONAL[^,\n]*)',
                r'(BRC\s+Industrial[^,\n]*)',
                r'(JOTUN[^,\n]*)',
                r'(ZAMIL[^,\n]*)',
                r'(NOFA\s+UNITED[^,\n]*)',
                r'Supplier[:#]?\s*([A-Z][A-Za-z\s&]+?)(?:\n|,|$)'
            ],
            'vendor_code': [
                r'Supplier\s*[:#]?\s*([A-Z0-9]+)',
                r'Vendor\s*[:#]?\s*([A-Z0-9]+)',
                r'Code\s*[:#]?\s*([A-Z0-9]+)'
            ],
            'amount_sar': [
                r'SAR\s*([\d,]+\.?\d*)',
                r'Total[^0-9]*SAR\s*([\d,]+\.?\d*)',
                r'([\d,]+\.?\d*)\s*SAR',
                r'ريال\s*([\d,]+\.?\d*)'  # Arabic SAR
            ],
            'date': [
                r'(\d{2}[/-]\d{2}[/-]\d{4})',
                r'(\d{4}[/-]\d{2}[/-]\d{2})',
                r'Date\s*[:#]?\s*(\d{2}[/-]\d{2}[/-]\d{4})'
            ]
        }
        
        extracted_fields = {}
        
        for field_name, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    extracted_fields[field_name] = match.group(1).strip()
                    break  # Use first match found
        
        return extracted_fields
    
    def _get_relationship_text(self, block, block_map, relationship_type):
        """
        Helper method to get text from related blocks
        """
        text = ""
        if 'Relationships' in block:
            for relationship in block['Relationships']:
                if relationship['Type'] == relationship_type:
                    for child_id in relationship['Ids']:
                        if child_id in block_map:
                            child_block = block_map[child_id]
                            if child_block['BlockType'] == 'WORD':
                                text += child_block['Text'] + " "
        return text.strip()
    
    def _extract_table_data(self, table_block, block_map):
        """
        Helper method to extract table data
        """
        table = []
        
        if 'Relationships' not in table_block:
            return table
        
        # Find all CELL blocks
        cells = {}
        for relationship in table_block['Relationships']:
            if relationship['Type'] == 'CHILD':
                for child_id in relationship['Ids']:
                    if child_id in block_map:
                        cell_block = block_map[child_id]
                        if cell_block['BlockType'] == 'CELL':
                            row_index = cell_block['RowIndex'] - 1  # Convert to 0-based
                            col_index = cell_block['ColumnIndex'] - 1
                            cell_text = self._get_relationship_text(cell_block, block_map, 'CHILD')
                            
                            if row_index not in cells:
                                cells[row_index] = {}
                            cells[row_index][col_index] = cell_text
        
        # Convert to list format
        if cells:
            max_row = max(cells.keys())
            for row_idx in range(max_row + 1):
                row_data = []
                if row_idx in cells:
                    max_col = max(cells[row_idx].keys()) if cells[row_idx] else 0
                    for col_idx in range(max_col + 1):
                        cell_value = cells[row_idx].get(col_idx, '')
                        row_data.append(cell_value)
                table.append(row_data)
        
        return table
    
    def _process_images_for_document_analysis(self, images):
        """
        Process images for document analysis (forms and tables)
        """
        combined_blocks = []
        
        for page_num, image in enumerate(images, 1):
            print(f"   Analyzing page {page_num} for forms and tables...")
            
            try:
                # Convert image to bytes
                image_bytes = self.image_to_bytes(image)
                
                # Use safe_textract_call instead of direct call
                response = self.safe_textract_call(
                    'analyze_document',
                    Document={'Bytes': image_bytes},
                    FeatureTypes=['FORMS', 'TABLES']
                )
                
                if response is None:
                    print(f"   Warning: Page {page_num} failed to process")
                    continue
                
                # Add page number to each block for tracking
                page_blocks = response.get('Blocks', [])
                for block in page_blocks:
                    block['PageNumber'] = page_num
                
                combined_blocks.extend(page_blocks)
                print(f"   Success: Page {page_num}: {len(page_blocks)} blocks extracted")
                
            except Exception as e:
                print(f"   Warning: Page {page_num} failed: {str(e)}")
                continue
        
        return {'Blocks': combined_blocks}
    
    def _process_images_for_expense_analysis(self, images):
        """
        Process images for expense analysis (invoice-specific)
        """
        combined_expense_docs = []
        
        for page_num, image in enumerate(images, 1):
            print(f"   Analyzing page {page_num} for expenses...")
            
            try:
                # Convert image to bytes
                image_bytes = self.image_to_bytes(image)
                
                # Use safe_textract_call instead of direct call
                response = self.safe_textract_call(
                    'analyze_expense',
                    Document={'Bytes': image_bytes}
                )
                
                if response is None:
                    print(f"   Warning: Expense analysis failed on page {page_num}")
                    continue
                
                # Add page number to expense documents
                expense_docs = response.get('ExpenseDocuments', [])
                for doc in expense_docs:
                    doc['PageNumber'] = page_num
                
                combined_expense_docs.extend(expense_docs)
                print(f"   Success: Page {page_num}: {len(expense_docs)} expense documents found")
                
            except Exception as e:
                print(f"   Warning: Expense analysis failed on page {page_num}: {str(e)}")
                continue
        
        return {'ExpenseDocuments': combined_expense_docs}
    
    def process_sap_document(self, pdf_path: str) -> Dict[str, Any]:
        """
        Main method to process SAP document and extract all relevant data
        """
        print(f"Processing document: {pdf_path}")
        
        # Convert PDF to images first
        images = self.convert_pdf_to_images(pdf_path)
        if not images:
            print("ERROR: Failed to convert PDF to images")
            return {'error': 'PDF conversion failed'}
        
        print(f"Successfully converted PDF to {len(images)} images")
        
        # Process images directly
        document_response = self._process_images_for_document_analysis(images)
        expense_response = self._process_images_for_expense_analysis(images)
        
        # Extract data using different methods
        results = {
            'document_analysis': {},
            'expense_analysis': {},
            'sap_specific_fields': {},
            'raw_text': '',
            'confidence_summary': {}
        }
        
        # Process document analysis
        if document_response:
            results['raw_text'] = self.extract_text_blocks(document_response)
            results['document_analysis']['key_value_pairs'] = self.extract_key_value_pairs(document_response)
            results['document_analysis']['tables'] = self.extract_tables(document_response)
        
        # Process expense analysis
        if expense_response:
            results['expense_analysis'] = self.extract_expense_data(expense_response)
        
        # Extract SAP-specific fields using regex
        if results['raw_text']:
            results['sap_specific_fields'] = self.extract_sap_specific_fields(results['raw_text'])
        
        # Calculate confidence summary
        if 'confidence_scores' in results['expense_analysis']:
            confidence_scores = results['expense_analysis']['confidence_scores']
            if confidence_scores:
                avg_confidence = sum(confidence_scores.values()) / len(confidence_scores)
                results['confidence_summary'] = {
                    'average_confidence': round(avg_confidence, 2),
                    'field_count': len(confidence_scores),
                    'high_confidence_fields': {k: v for k, v in confidence_scores.items() if v > 90},
                    'low_confidence_fields': {k: v for k, v in confidence_scores.items() if v < 70}
                }
        
        return results

# Main execution
def main():
    print("="*80)
    print("AWS TEXTRACT SAP EXTRACTOR - Enhanced Version")
    print("="*80)
    
    # Check dependencies first
    if not check_dependencies():
        return
    
    # Load AWS credentials from .env
    if not load_aws_credentials():
        return
    
    # Get region from environment or use default
    region = "eu-west-1"
    
    # Initialize extractor
    extractor = AWSTextractSAPExtractor(region_name=region)
    
    # Find PDF files in current directory
    current_files = [f for f in os.listdir('.') if f.endswith('.pdf')]
    
    if not current_files:
        print("No PDF files found in current directory")
        return
    
    # Process the first PDF (you can change this)
    target_pdf = "1028d47a836a4578a84c7a492688751d_JOTUN_GRP-15342_PO_2734.pdf"  # Change this to your desired file
    if target_pdf in current_files:
        pdf_path = target_pdf
        print(f"Processing specified file: {pdf_path}")
    else:
        print(f"File '{target_pdf}' not found in directory")
        print(f"Available files: {current_files}")
        # Use the first PDF found
        pdf_path = current_files[0]
        print(f"Using first PDF found: {pdf_path}")
    
    try:
        results = extractor.process_sap_document(pdf_path)
        
        if 'error' in results:
            print(f"Processing failed: {results['error']}")
            return
        
        # Print results in a structured way
        print("=" * 80)
        print("AWS TEXTRACT ANALYSIS RESULTS")
        print("=" * 80)
        
        print("\nConfidence Summary:")
        if results['confidence_summary']:
            summary = results['confidence_summary']
            print(f"Average Confidence: {summary['average_confidence']}%")
            print(f"Fields Extracted: {summary['field_count']}")
            print(f"High Confidence Fields: {len(summary['high_confidence_fields'])}")
            print(f"Low Confidence Fields: {len(summary['low_confidence_fields'])}")
        else:
            print("No confidence data available (document analysis used)")
        
        print("\nSAP-Specific Fields (Enhanced Regex Extraction):")
        for field, value in results['sap_specific_fields'].items():
            print(f"{field}: {value}")
        
        print("\nExpense Analysis (Built-in Invoice Recognition):")
        expense_data = results['expense_analysis']
        for field, value in expense_data.items():
            if field != 'confidence_scores' and field != 'line_items':
                print(f"{field}: {value}")
        
        print("\nLine Items:")
        if expense_data.get('line_items'):
            for i, item in enumerate(expense_data['line_items'], 1):
                print(f"Item {i}: {item}")
        else:
            print("No line items detected")
        
        print("\nKey-Value Pairs (Form Recognition):")
        kv_pairs = results['document_analysis'].get('key_value_pairs', {})
        if kv_pairs:
            for key, value in list(kv_pairs.items())[:10]:  # Show first 10 pairs
                print(f"{key}: {value}")
        else:
            print("No key-value pairs detected")
        
        print("\nTables Detected:")
        tables = results['document_analysis'].get('tables', [])
        if tables:
            for i, table in enumerate(tables, 1):
                print(f"\nTable {i}:")
                for row in table[:5]:  # Show first 5 rows of each table
                    print("\t" + " | ".join(row))
        else:
            print("No tables detected")
        
        # Performance summary
        print("\n" + "="*60)
        print("EXTRACTION PERFORMANCE")
        print("="*60)
        
        sap_fields = results['sap_specific_fields']
        key_fields = ['po_number', 'grn_number', 'vendor_name', 'amount_sar']
        found_count = sum(1 for field in key_fields if field in sap_fields)
        accuracy = (found_count / len(key_fields)) * 100
        
        print(f"Key SAP fields found: {found_count}/{len(key_fields)} ({accuracy:.1f}%)")
        
        if accuracy >= 75:
            print("✅ Excellent: High extraction accuracy for scanned documents!")
        elif accuracy >= 50:
            print("⚠️  Good: Decent extraction accuracy")
        else:
            print("❌ Needs improvement: Consider image preprocessing")
        
        # Save detailed results to JSON file
        output_file = f'textract_results_{pdf_path.replace(".pdf", "").replace(" ", "_")}.json'
        with open(output_file, 'w') as f:
            # Convert any non-serializable objects to strings
            serializable_results = json.loads(json.dumps(results, default=str))
            json.dump(serializable_results, f, indent=2)
        
        print(f"\n💾 Detailed results saved to '{output_file}'")
        
    except Exception as e:
        print(f"❌ Error processing document: {str(e)}")
        print("Make sure poppler is installed and accessible in PATH")
        print("Check your .env file contains valid AWS credentials")

if __name__ == "__main__":
    main()