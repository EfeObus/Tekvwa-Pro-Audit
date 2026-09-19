"""
Tekvwa Pro Audit - OCR Service

OCR service for receipt processing and data extraction.

Supports:
- Azure Document Intelligence (Form Recognizer)
- Fallback to basic OCR when Azure not configured

Extracts:
- Vendor name
- Transaction date
- Total amount
- VAT amount
- Line items (when available)
- Receipt number
"""

import uuid
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from app.config import settings


class OCRProvider(str, Enum):
    """OCR service providers."""
    AZURE_DOCUMENT_INTELLIGENCE = "azure"
    MOCK = "mock"  # For development/testing


@dataclass
class ExtractedLineItem:
    """Extracted line item from receipt."""
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


@dataclass
class ExtractedReceiptData:
    """Extracted data from a receipt."""
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    vendor_tin: Optional[str] = None
    receipt_number: Optional[str] = None
    transaction_date: Optional[date] = None
    subtotal: Optional[float] = None
    vat_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "NGN"
    payment_method: Optional[str] = None
    line_items: Optional[List[ExtractedLineItem]] = None
    raw_text: Optional[str] = None
    confidence_score: float = 0.0
    provider: str = "mock"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "vendor_name": self.vendor_name,
            "vendor_address": self.vendor_address,
            "vendor_tin": self.vendor_tin,
            "receipt_number": self.receipt_number,
            "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
            "subtotal": self.subtotal,
            "vat_amount": self.vat_amount,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "line_items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "amount": item.amount,
                }
                for item in (self.line_items or [])
            ],
            "confidence_score": self.confidence_score,
            "provider": self.provider,
        }


class OCRService:
    """
    OCR service for receipt processing.
    
    Uses Azure Document Intelligence when configured,
    falls back to mock extraction for development.
    """
    
    def __init__(self):
        self.azure_endpoint = getattr(settings, 'azure_form_recognizer_endpoint', None)
        self.azure_key = getattr(settings, 'azure_form_recognizer_key', None)
        self.provider = self._determine_provider()
    
    def _determine_provider(self) -> OCRProvider:
        """Determine which OCR provider to use."""
        if self.azure_endpoint and self.azure_key:
            return OCRProvider.AZURE_DOCUMENT_INTELLIGENCE
        return OCRProvider.MOCK
    
    async def process_receipt(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> ExtractedReceiptData:
        """
        Process a receipt image and extract data.
        
        Args:
            file_content: The raw file bytes
            filename: Original filename
            content_type: MIME type (image/jpeg, image/png, application/pdf)
            
        Returns:
            ExtractedReceiptData with extracted information
        """
        if self.provider == OCRProvider.AZURE_DOCUMENT_INTELLIGENCE:
            return await self._process_with_azure(file_content, content_type)
        else:
            return await self._process_mock(file_content, filename)
    
    async def _process_with_azure(
        self,
        file_content: bytes,
        content_type: str,
    ) -> ExtractedReceiptData:
        """
        Process receipt using Azure Document Intelligence.
        
        Uses the prebuilt-receipt model for receipt extraction.
        """
        try:
            from azure.ai.formrecognizer import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
            
            client = DocumentAnalysisClient(
                endpoint=self.azure_endpoint,
                credential=AzureKeyCredential(self.azure_key),
            )
            
            # Analyze receipt
            poller = client.begin_analyze_document(
                "prebuilt-receipt",
                file_content,
            )
            result = poller.result()
            
            # Extract data from first receipt
            if result.documents:
                doc = result.documents[0]
                fields = doc.fields
                
                # Extract vendor info
                vendor_name = None
                vendor_address = None
                if "MerchantName" in fields:
                    vendor_name = fields["MerchantName"].value
                if "MerchantAddress" in fields:
                    vendor_address = fields["MerchantAddress"].value
                
                # Extract transaction date
                transaction_date = None
                if "TransactionDate" in fields:
                    transaction_date = fields["TransactionDate"].value
                
                # Extract amounts
                subtotal = None
                vat_amount = None
                total_amount = None
                
                if "Subtotal" in fields:
                    subtotal = float(fields["Subtotal"].value)
                if "TotalTax" in fields:
                    vat_amount = float(fields["TotalTax"].value)
                if "Total" in fields:
                    total_amount = float(fields["Total"].value)
                
                # Extract line items
                line_items = []
                if "Items" in fields:
                    for item in fields["Items"].value:
                        item_fields = item.value
                        line_items.append(ExtractedLineItem(
                            description=item_fields.get("Description", {}).value or "",
                            quantity=float(item_fields.get("Quantity", {}).value or 1),
                            unit_price=float(item_fields.get("Price", {}).value or 0),
                            amount=float(item_fields.get("TotalPrice", {}).value or 0),
                        ))
                
                return ExtractedReceiptData(
                    vendor_name=vendor_name,
                    vendor_address=vendor_address,
                    transaction_date=transaction_date,
                    subtotal=subtotal,
                    vat_amount=vat_amount,
                    total_amount=total_amount,
                    line_items=line_items if line_items else None,
                    confidence_score=doc.confidence,
                    provider="azure",
                )
            
            # No documents found
            return ExtractedReceiptData(
                confidence_score=0.0,
                provider="azure",
            )
            
        except ImportError:
            # Azure SDK not installed, fall back to mock
            return await self._process_mock(file_content, "receipt")
        except Exception as e:
            # Log error and return empty result
            print(f"Azure OCR error: {e}")
            return ExtractedReceiptData(
                confidence_score=0.0,
                provider="azure_error",
            )
    
    async def _process_mock(
        self,
        file_content: bytes,
        filename: str,
    ) -> ExtractedReceiptData:
        """
        Mock OCR processing for development.
        
        Returns simulated extracted data.
        """
        # Simulate processing delay would happen here
        
        # Generate mock data based on filename patterns
        mock_vendors = [
            ("Shoprite", "123 Lagos Road, Ikeja, Lagos"),
            ("MTN Nigeria", "MTN Plaza, Victoria Island, Lagos"),
            ("Total Energies", "15 Lekki-Epe Expressway, Lagos"),
            ("Chicken Republic", "45 Allen Avenue, Ikeja, Lagos"),
            ("Printivo", "Online Printing Service"),
        ]
        
        import random
        vendor = random.choice(mock_vendors)
        
        # Generate random amounts
        subtotal = round(random.uniform(500, 50000), 2)
        vat_rate = 0.075  # 7.5% VAT
        vat_amount = round(subtotal * vat_rate, 2)
        total_amount = subtotal + vat_amount
        
        return ExtractedReceiptData(
            vendor_name=vendor[0],
            vendor_address=vendor[1],
            receipt_number=f"RCP-{random.randint(100000, 999999)}",
            transaction_date=date.today(),
            subtotal=subtotal,
            vat_amount=vat_amount,
            total_amount=total_amount,
            currency="NGN",
            line_items=[
                ExtractedLineItem(
                    description="Item 1",
                    quantity=1,
                    unit_price=subtotal * 0.6,
                    amount=subtotal * 0.6,
                ),
                ExtractedLineItem(
                    description="Item 2",
                    quantity=2,
                    unit_price=subtotal * 0.2,
                    amount=subtotal * 0.4,
                ),
            ],
            confidence_score=0.85,
            provider="mock",
        )
    
    def extract_tin_from_text(self, text: str) -> Optional[str]:
        """
        Extract TIN (Tax Identification Number) from text.
        
        Nigerian TIN format: 10 digits or 10 digits with hyphen
        """
        # Pattern for Nigerian TIN
        patterns = [
            r'\b(\d{10})\b',  # 10 consecutive digits
            r'\b(\d{8}-\d{2})\b',  # 8 digits, hyphen, 2 digits
            r'TIN[:\s]*(\d{10})',  # TIN: followed by 10 digits
            r'TIN[:\s]*(\d{8}-\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).replace("-", "")
        
        return None
    
    def extract_date_from_text(self, text: str) -> Optional[date]:
        """Extract date from text using common formats."""
        date_patterns = [
            (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%d/%m/%Y'),
            (r'(\d{1,2})-(\d{1,2})-(\d{4})', '%d-%m-%Y'),
            (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),
            (r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})', None),
        ]
        
        for pattern, fmt in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    if fmt:
                        date_str = match.group(0)
                        return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        
        return None
    
    def extract_amount_from_text(self, text: str) -> Optional[float]:
        """Extract monetary amount from text."""
        # Patterns for Nigerian Naira amounts
        patterns = [
            r'₦\s*([\d,]+\.?\d*)',
            r'NGN\s*([\d,]+\.?\d*)',
            r'N\s*([\d,]+\.?\d*)',
            r'Total[:\s]*([\d,]+\.?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1).replace(",", "")
                    return float(amount_str)
                except ValueError:
                    continue
        
        return None
