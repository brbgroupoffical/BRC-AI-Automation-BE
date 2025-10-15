from django.db import transaction
from datetime import datetime
from decimal import Decimal
from grn_automation.models import DocumentLine, GRNAutomation, ValidationResult


def save_validation_results(automation_id, validation_data):
    """
    Save validation results to the database.
    
    Args:
        automation_id: ID of the GRNAutomation instance
        validation_data: Dictionary containing validation results
        
    Returns:
        dict: Summary of saved data
        
    Example validation_data structure:
        {
            'status': 'success',
            'message': 'Validation message...',
            'data': {
                'validation_results': [
                    {
                        'invoice_date': '2025-08-23',
                        'status': ValidationStatus.SUCCESS,
                        'payload': {
                            'CardCode': 'S01609',
                            'DocEntry': 20283,
                            'DocDate': '2025-08-23',
                            'BPL_IDAssignedToInvoice': 3,
                            'DocumentLines': [
                                {'LineNum': 0, 'RemainingOpenQuantity': 50.0},
                                ...
                            ]
                        }
                    },
                    ...
                ]
            }
        }
    """
    try:
        with transaction.atomic():
            # Get the automation instance
            automation = GRNAutomation.objects.get(id=automation_id)
            
            # Store the validation message
            automation.validation_message = validation_data.get('message', '')
            automation.save(update_fields=['validation_message'])
            
            # Extract validation results
            validation_results_data = validation_data.get('data', {}).get('validation_results', [])
            
            summary = {
                'automation_id': automation_id,
                'total_validations': 0,
                'total_document_lines': 0,
                'validation_result_ids': []
            }
            
            # Process each validation result
            for result_data in validation_results_data:
                invoice_date_str = result_data.get('invoice_date')
                validation_status = result_data.get('status')
                payload = result_data.get('payload', {})
                
                # Convert invoice_date string to date object
                if isinstance(invoice_date_str, str):
                    invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
                else:
                    invoice_date = invoice_date_str
                
                # Handle ValidationStatus enum or string
                if hasattr(validation_status, 'value'):
                    status_value = validation_status.value
                else:
                    status_value = str(validation_status).upper()
                
                # Create ValidationResult instance
                validation_result = ValidationResult.objects.create(
                    automation=automation,
                    invoice_date=invoice_date,
                    validation_status=status_value,
                    card_code=payload.get('CardCode', ''),
                    doc_entry=payload.get('DocEntry', 0),
                    doc_date=datetime.strptime(payload.get('DocDate', invoice_date_str), '%Y-%m-%d').date(),
                    bpl_id=payload.get('BPL_IDAssignedToInvoice', 0),
                    posting_status=ValidationResult.PostingStatus.PENDING,
                    posting_message=''
                )
                
                summary['validation_result_ids'].append(validation_result.id)
                summary['total_validations'] += 1
                
                # Process document lines
                document_lines_data = payload.get('DocumentLines', [])
                document_lines = []
                
                for line_data in document_lines_data:
                    line_num = line_data.get('LineNum', 0)
                    remaining_qty = line_data.get('RemainingOpenQuantity', 0.0)
                    
                    # Convert to Decimal for precision
                    if not isinstance(remaining_qty, Decimal):
                        remaining_qty = Decimal(str(remaining_qty))
                    
                    document_line = DocumentLine(
                        validation_result=validation_result,
                        line_num=line_num,
                        remaining_open_quantity=remaining_qty
                    )
                    document_lines.append(document_line)
                    summary['total_document_lines'] += 1
                
                # Bulk create document lines for efficiency
                if document_lines:
                    DocumentLine.objects.bulk_create(document_lines)
            
            return {
                'success': True,
                'summary': summary
            }
            
    except GRNAutomation.DoesNotExist:
        return {
            'success': False,
            'error': f'GRNAutomation with id {automation_id} does not exist'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# Usage example:
def process_validation_response(automation_id, response_data):
    """
    Wrapper function to process validation response and save to DB.
    
    Args:
        automation_id: ID of the automation
        response_data: Response from validation function (any of the three cases)
    """
    result = save_validation_results(automation_id, response_data)
    
    if result['success']:
        print(f"✅ Successfully saved validation results")
        print(f"📊 Summary: {result['summary']}")
    else:
        print(f"❌ Error: {result['error']}")
    
    return result