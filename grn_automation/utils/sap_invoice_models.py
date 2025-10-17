from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class ValidationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED" 
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class DocumentLine(BaseModel):
    """SAP B1 Document Line for AP Invoice"""
    BaseType: int = Field(default=20, description="Source Object (20 = Good Receipt PO)")
    BaseEntry: int = Field(description="The GRPO document's ID from SAP")
    BaseLine: int = Field(description="The specific line number in the GRPO")
    Quantity: float = Field(description="Units invoiced from that GRPO line")
    UnitPrice: float = Field(description="Price per unit for invoicing")


class APInvoicePayload(BaseModel):
    """SAP B1 Purchase Invoice API payload structure"""
    CardCode: str = Field(description="Vendor ID/Code from SAP")
    DocDate: str = Field(description="Invoice posting date (YYYY-MM-DD format)")
    DocumentLines: List[DocumentLine] = Field(description="List of invoice line items")


class ValidationResult(BaseModel):
    """Simplified validation result with only essential fields"""
    
    status: ValidationStatus = Field(description="Validation status: SUCCESS, FAILED, or REQUIRES_REVIEW")
    reasoning: str = Field(description="Brief explanation of validation decision (2-3 lines max)")
    payload: Optional[APInvoicePayload] = Field(
        default=None,
        description="SAP AP Invoice payload (only if status is SUCCESS)"
    )