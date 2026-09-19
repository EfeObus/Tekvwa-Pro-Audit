"""
Tekvwa Pro Audit - Invoice PDF Service

Generates professional PDF invoices for billing transactions.
Uses ReportLab for PDF generation with Nigerian business formatting.

Features:
- Company branding and logo
- Nigerian tax compliance (VAT registration, TIN)
- Currency formatting in Naira
- Line item details
- Payment instructions
- Digital signatures (optional)
"""

import io
import logging
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class InvoiceLineItem:
    """Line item for invoice."""
    description: str
    quantity: int
    unit_price_naira: int
    total_naira: int
    
    @property
    def unit_price_formatted(self) -> str:
        return f"₦{self.unit_price_naira:,}"
    
    @property
    def total_formatted(self) -> str:
        return f"₦{self.total_naira:,}"


@dataclass
class InvoiceData:
    """Data structure for invoice generation."""
    # Invoice details
    invoice_number: str
    invoice_date: date
    due_date: date
    
    # Customer/Organization details
    customer_name: str
    customer_email: str
    customer_address: Optional[str] = None
    customer_tin: Optional[str] = None
    
    # Line items
    line_items: List[InvoiceLineItem] = None
    
    # Amounts
    subtotal_naira: int = 0
    vat_naira: int = 0
    total_naira: int = 0
    
    # Payment details
    payment_reference: Optional[str] = None
    payment_status: str = "unpaid"
    payment_method: Optional[str] = None
    paid_at: Optional[datetime] = None
    
    # Additional info
    notes: Optional[str] = None
    terms: Optional[str] = None
    
    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []


class InvoicePDFService:
    """Service for generating PDF invoices."""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        
        # Company details from settings
        self.company_name = getattr(settings, 'company_name', 'Tekvwa Pro Audit')
        self.company_address = getattr(settings, 'company_address', 'Lagos, Nigeria')
        self.company_email = getattr(settings, 'company_email', 'info@tekvwa.org')
        self.company_phone = getattr(settings, 'company_phone', '+234-XXX-XXX-XXXX')
        self.company_tin = getattr(settings, 'company_tin', '')
        self.company_vat_id = getattr(settings, 'company_vat_id', '')
        self.company_rc_number = getattr(settings, 'company_rc_number', '')
        
        # Bank details for payment
        self.bank_name = getattr(settings, 'bank_name', '')
        self.bank_account_name = getattr(settings, 'bank_account_name', '')
        self.bank_account_number = getattr(settings, 'bank_account_number', '')
        
        # Logo path
        self.logo_path = getattr(settings, 'company_logo_path', None)
        
        # VAT rate (7.5% in Nigeria)
        self.vat_rate = Decimal("0.075")
    
    def _format_naira(self, amount: int) -> str:
        """Format amount as Nigerian Naira."""
        return f"₦{amount:,}"
    
    async def generate_subscription_invoice(
        self,
        organization_id: uuid.UUID,
        tier: str,
        billing_cycle: str,
        amount_naira: int,
        payment_reference: str,
        invoice_number: Optional[str] = None,
        paid_at: Optional[datetime] = None,
    ) -> bytes:
        """
        Generate invoice PDF for a subscription payment.
        
        Args:
            organization_id: Customer organization ID
            tier: Subscription tier (core, professional, enterprise)
            billing_cycle: monthly or annual
            amount_naira: Total amount in Naira
            payment_reference: Payment reference number
            invoice_number: Optional invoice number (auto-generated if not provided)
            paid_at: When payment was received (None for unpaid)
            
        Returns:
            PDF bytes
        """
        from app.models.organization import Organization
        from app.models.user import User
        from sqlalchemy import select
        
        # Get organization details
        if self.db:
            org_result = await self.db.execute(
                select(Organization).where(Organization.id == organization_id)
            )
            org = org_result.scalar_one_or_none()
            
            # Get admin user for contact details
            admin_result = await self.db.execute(
                select(User)
                .where(User.organization_id == organization_id)
                .where(User.is_active == True)
                .order_by(User.created_at)
                .limit(1)
            )
            admin_user = admin_result.scalar_one_or_none()
            
            customer_name = org.name if org else "Customer"
            customer_email = admin_user.email if admin_user else ""
            customer_address = getattr(org, 'address', None) if org else None
            customer_tin = getattr(org, 'tin', None) if org else None
        else:
            customer_name = "Customer"
            customer_email = ""
            customer_address = None
            customer_tin = None
        
        # Generate invoice number if not provided
        if not invoice_number:
            date_prefix = datetime.now().strftime("%Y%m")
            invoice_number = f"INV-{date_prefix}-{payment_reference[:8].upper()}"
        
        # Calculate VAT (7.5% of subtotal)
        subtotal = int(amount_naira / Decimal("1.075"))  # Amount is VAT-inclusive
        vat = amount_naira - subtotal
        
        # Create line items
        tier_display = f"Pro Audit {tier.title()}"
        cycle_display = "Annual" if billing_cycle == "annual" else "Monthly"
        
        line_items = [
            InvoiceLineItem(
                description=f"{tier_display} Subscription ({cycle_display})",
                quantity=1,
                unit_price_naira=subtotal,
                total_naira=subtotal,
            )
        ]
        
        # Create invoice data
        invoice_data = InvoiceData(
            invoice_number=invoice_number,
            invoice_date=date.today(),
            due_date=date.today() if paid_at else (date.today() + timedelta(days=7)),
            customer_name=customer_name,
            customer_email=customer_email,
            customer_address=customer_address,
            customer_tin=customer_tin,
            line_items=line_items,
            subtotal_naira=subtotal,
            vat_naira=vat,
            total_naira=amount_naira,
            payment_reference=payment_reference,
            payment_status="paid" if paid_at else "unpaid",
            paid_at=paid_at,
            notes="Thank you for your subscription!",
            terms="Payment is due upon receipt. All amounts are in Nigerian Naira (NGN).",
        )
        
        return self.generate_invoice_pdf(invoice_data)
    
    def generate_invoice_pdf(self, invoice: InvoiceData) -> bytes:
        """
        Generate a PDF invoice from invoice data.
        
        Args:
            invoice: InvoiceData object with all invoice details
            
        Returns:
            PDF bytes
        """
        if not REPORTLAB_AVAILABLE:
            logger.warning("ReportLab not available, generating simple text invoice")
            return self._generate_text_invoice(invoice)
        
        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm,
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=12,
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a365d'),
            spaceBefore=12,
            spaceAfter=6,
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=4,
        )
        
        right_style = ParagraphStyle(
            'RightAlign',
            parent=styles['Normal'],
            fontSize=10,
            alignment=TA_RIGHT,
        )
        
        # Build document content
        elements = []
        
        # Header with company info
        elements.append(self._build_header(styles, title_style))
        elements.append(Spacer(1, 20))
        
        # Invoice title and status
        status_color = colors.green if invoice.payment_status == "paid" else colors.orange
        status_text = "PAID" if invoice.payment_status == "paid" else "UNPAID"
        
        elements.append(Paragraph(f"INVOICE", title_style))
        elements.append(Paragraph(
            f'<font color="{status_color.hexval()}">{status_text}</font>',
            right_style
        ))
        elements.append(Spacer(1, 10))
        
        # Invoice details and customer info side by side
        elements.append(self._build_info_section(invoice, normal_style, heading_style))
        elements.append(Spacer(1, 20))
        
        # Line items table
        elements.append(Paragraph("Items", heading_style))
        elements.append(self._build_items_table(invoice))
        elements.append(Spacer(1, 20))
        
        # Totals
        elements.append(self._build_totals_section(invoice, normal_style, right_style))
        elements.append(Spacer(1, 20))
        
        # Payment info
        if invoice.payment_status != "paid":
            elements.append(self._build_payment_section(invoice, normal_style, heading_style))
            elements.append(Spacer(1, 20))
        
        # Notes and terms
        if invoice.notes:
            elements.append(Paragraph("Notes", heading_style))
            elements.append(Paragraph(invoice.notes, normal_style))
            elements.append(Spacer(1, 10))
        
        if invoice.terms:
            elements.append(Paragraph("Terms & Conditions", heading_style))
            elements.append(Paragraph(invoice.terms, normal_style))
        
        # Footer
        elements.append(Spacer(1, 30))
        elements.append(self._build_footer(normal_style))
        
        # Build PDF
        doc.build(elements)
        
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        return pdf_bytes
    
    def _build_header(self, styles, title_style):
        """Build invoice header with company info."""
        header_data = [
            [
                Paragraph(f"<b>{self.company_name}</b>", title_style),
                "",
            ],
            [
                Paragraph(self.company_address, styles['Normal']),
                "",
            ],
            [
                Paragraph(f"Email: {self.company_email}", styles['Normal']),
                "",
            ],
            [
                Paragraph(f"Phone: {self.company_phone}", styles['Normal']),
                "",
            ],
        ]
        
        if self.company_tin:
            header_data.append([
                Paragraph(f"TIN: {self.company_tin}", styles['Normal']),
                "",
            ])
        
        if self.company_vat_id:
            header_data.append([
                Paragraph(f"VAT ID: {self.company_vat_id}", styles['Normal']),
                "",
            ])
        
        header_table = Table(header_data, colWidths=[300, 200])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        return header_table
    
    def _build_info_section(self, invoice: InvoiceData, normal_style, heading_style):
        """Build invoice info and customer section."""
        # Left: Invoice details
        invoice_info = f"""
        <b>Invoice Number:</b> {invoice.invoice_number}<br/>
        <b>Invoice Date:</b> {invoice.invoice_date.strftime('%B %d, %Y')}<br/>
        <b>Due Date:</b> {invoice.due_date.strftime('%B %d, %Y')}<br/>
        """
        
        if invoice.payment_reference:
            invoice_info += f"<b>Reference:</b> {invoice.payment_reference}<br/>"
        
        if invoice.paid_at:
            invoice_info += f"<b>Paid On:</b> {invoice.paid_at.strftime('%B %d, %Y')}<br/>"
        
        # Right: Customer details
        customer_info = f"""
        <b>Bill To:</b><br/>
        {invoice.customer_name}<br/>
        {invoice.customer_email}<br/>
        """
        
        if invoice.customer_address:
            customer_info += f"{invoice.customer_address}<br/>"
        
        if invoice.customer_tin:
            customer_info += f"TIN: {invoice.customer_tin}<br/>"
        
        info_data = [
            [
                Paragraph(invoice_info, normal_style),
                Paragraph(customer_info, normal_style),
            ]
        ]
        
        info_table = Table(info_data, colWidths=[250, 250])
        info_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        return info_table
    
    def _build_items_table(self, invoice: InvoiceData):
        """Build line items table."""
        # Header
        data = [
            ['Description', 'Qty', 'Unit Price', 'Total']
        ]
        
        # Items
        for item in invoice.line_items:
            data.append([
                item.description,
                str(item.quantity),
                item.unit_price_formatted,
                item.total_formatted,
            ])
        
        table = Table(data, colWidths=[250, 50, 100, 100])
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            
            # Row styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 8),
            
            # Alignment
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            
            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ]))
        
        return table
    
    def _build_totals_section(self, invoice: InvoiceData, normal_style, right_style):
        """Build totals section."""
        totals_data = [
            ['', '', 'Subtotal:', self._format_naira(invoice.subtotal_naira)],
            ['', '', 'VAT (7.5%):', self._format_naira(invoice.vat_naira)],
            ['', '', 'Total:', self._format_naira(invoice.total_naira)],
        ]
        
        totals_table = Table(totals_data, colWidths=[250, 50, 100, 100])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEABOVE', (2, -1), (-1, -1), 1, colors.black),
        ]))
        
        return totals_table
    
    def _build_payment_section(self, invoice: InvoiceData, normal_style, heading_style):
        """Build payment instructions section."""
        elements = []
        
        elements.append(Paragraph("Payment Instructions", heading_style))
        
        if self.bank_name and self.bank_account_number:
            payment_info = f"""
            <b>Bank Transfer:</b><br/>
            Bank: {self.bank_name}<br/>
            Account Name: {self.bank_account_name}<br/>
            Account Number: {self.bank_account_number}<br/>
            <br/>
            Please use invoice number <b>{invoice.invoice_number}</b> as payment reference.
            """
        else:
            payment_info = f"""
            Please pay using your preferred payment method.<br/>
            Use reference: <b>{invoice.payment_reference or invoice.invoice_number}</b>
            """
        
        elements.append(Paragraph(payment_info, normal_style))
        
        return elements
    
    def _build_footer(self, normal_style):
        """Build invoice footer."""
        footer_text = f"""
        <para align="center">
        Thank you for your business!<br/>
        Questions? Contact us at {self.company_email}
        </para>
        """
        
        return Paragraph(footer_text, normal_style)
    
    def _generate_text_invoice(self, invoice: InvoiceData) -> bytes:
        """Generate simple text invoice when ReportLab is not available."""
        lines = [
            "=" * 60,
            f"                    {self.company_name}",
            f"                    INVOICE",
            "=" * 60,
            "",
            f"Invoice Number: {invoice.invoice_number}",
            f"Invoice Date:   {invoice.invoice_date.strftime('%B %d, %Y')}",
            f"Due Date:       {invoice.due_date.strftime('%B %d, %Y')}",
            f"Status:         {invoice.payment_status.upper()}",
            "",
            "-" * 60,
            "BILL TO:",
            f"  {invoice.customer_name}",
            f"  {invoice.customer_email}",
        ]
        
        if invoice.customer_address:
            lines.append(f"  {invoice.customer_address}")
        
        lines.extend([
            "",
            "-" * 60,
            "ITEMS:",
            "-" * 60,
        ])
        
        for item in invoice.line_items:
            lines.append(f"  {item.description}")
            lines.append(f"    Qty: {item.quantity} x {item.unit_price_formatted} = {item.total_formatted}")
        
        lines.extend([
            "",
            "-" * 60,
            f"                              Subtotal: {self._format_naira(invoice.subtotal_naira)}",
            f"                              VAT (7.5%): {self._format_naira(invoice.vat_naira)}",
            "                              " + "-" * 20,
            f"                              TOTAL: {self._format_naira(invoice.total_naira)}",
            "",
            "=" * 60,
        ])
        
        if invoice.notes:
            lines.extend([
                "",
                f"Notes: {invoice.notes}",
            ])
        
        lines.extend([
            "",
            f"Thank you for your business!",
            f"Questions? Contact us at {self.company_email}",
            "",
        ])
        
        return "\n".join(lines).encode('utf-8')


# Import timedelta for use in generate_subscription_invoice
from datetime import timedelta
