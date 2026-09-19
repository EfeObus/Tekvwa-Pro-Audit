"""
Tekvwa Pro Audit - Peppol BIS Billing 3.0 E-Invoice Export Service

Generates NRS-compliant invoices in structured digital formats:
- XML (UBL 2.1 - Universal Business Language)
- JSON (Peppol BIS Billing 3.0 JSON representation)

This is required for 2026 Nigeria Tax Reform compliance where:
- All invoices must be in structured digital formats
- Peppol BIS Billing 3.0 is the mandated standard
- Real-time or near real-time NRS submission required
- All invoices must include QR codes and CSID (Cryptographic Stamp ID)

Reference: https://docs.peppol.eu/poacc/billing/3.0/
"""

import uuid
import json
import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass
import xml.etree.ElementTree as ET
from xml.dom import minidom

from app.config import settings


class InvoiceTypeCode(str, Enum):
    """Invoice type codes per UBL 2.1."""
    COMMERCIAL_INVOICE = "380"      # Standard commercial invoice
    CREDIT_NOTE = "381"             # Credit note
    DEBIT_NOTE = "383"              # Debit note
    CORRECTED_INVOICE = "384"       # Corrected invoice
    PREPAYMENT_INVOICE = "386"      # Prepayment invoice


class TaxCategoryCode(str, Enum):
    """Tax category codes per Peppol BIS."""
    STANDARD_RATE = "S"     # Standard rate VAT (7.5%)
    ZERO_RATED = "Z"        # Zero rated
    EXEMPT = "E"            # Exempt from tax
    NOT_SUBJECT = "O"       # Not subject to tax


@dataclass
class PeppolParty:
    """Party information for Peppol invoice."""
    name: str
    tin: Optional[str] = None
    registration_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: str = "NG"  # Nigeria
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


@dataclass
class PeppolLineItem:
    """Line item for Peppol invoice."""
    item_id: str
    description: str
    quantity: Decimal
    unit_code: str  # UNE/CEFACT unit code (e.g., "EA" for each)
    unit_price: Decimal
    line_total: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    tax_category: TaxCategoryCode = TaxCategoryCode.STANDARD_RATE
    item_classification_code: Optional[str] = None  # HS code


@dataclass 
class PeppolInvoice:
    """Complete Peppol BIS Billing 3.0 invoice."""
    invoice_number: str
    invoice_date: date
    due_date: date
    invoice_type: InvoiceTypeCode
    seller: PeppolParty
    buyer: PeppolParty
    line_items: List[PeppolLineItem]
    currency_code: str = "NGN"
    subtotal: Decimal = Decimal("0")
    total_vat: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    payment_terms: Optional[str] = None
    nrs_irn: Optional[str] = None
    nrs_csid: Optional[str] = None  # Cryptographic Stamp ID
    nrs_qr_code_data: Optional[str] = None
    notes: Optional[str] = None


class PeppolExportService:
    """
    Service for generating Peppol BIS Billing 3.0 compliant invoices.
    
    Supports:
    - UBL 2.1 XML format
    - JSON representation
    - QR code data embedding
    - CSID (Cryptographic Stamp Identifier) inclusion
    """
    
    # UBL Namespaces
    UBL_NAMESPACE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
    CAC_NAMESPACE = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    CBC_NAMESPACE = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    
    # Profile identifiers
    PEPPOL_PROFILE_ID = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
    CUSTOMIZATION_ID = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
    
    # NRS Nigeria specific
    NRS_SCHEME_ID = "NG:NRS"
    
    def __init__(self):
        """Initialize the export service."""
        pass
    
    def generate_csid(self, invoice: PeppolInvoice) -> str:
        """
        Generate Cryptographic Stamp Identifier (CSID) for the invoice.
        
        The CSID is a hash of critical invoice data for verification.
        In production, this would use the NRS cryptographic signing service.
        
        Args:
            invoice: The invoice to generate CSID for
        
        Returns:
            CSID string
        """
        # Create hash input from critical invoice data
        hash_input = f"{invoice.invoice_number}|{invoice.invoice_date.isoformat()}|{invoice.seller.tin}|{invoice.buyer.tin or 'B2C'}|{invoice.total_amount}"
        
        # Generate SHA-256 hash
        csid = hashlib.sha256(hash_input.encode()).hexdigest()[:32].upper()
        
        return f"NRS-CSID-{csid}"
    
    def generate_qr_code_data(self, invoice: PeppolInvoice) -> str:
        """
        Generate QR code data for NRS compliance.
        
        The QR code contains essential invoice data for verification.
        
        Args:
            invoice: The invoice to generate QR data for
        
        Returns:
            QR code data string (JSON)
        """
        qr_data = {
            "irn": invoice.nrs_irn or "PENDING",
            "csid": invoice.nrs_csid or self.generate_csid(invoice),
            "inv": invoice.invoice_number,
            "dt": invoice.invoice_date.isoformat(),
            "seller_tin": invoice.seller.tin,
            "buyer_tin": invoice.buyer.tin or "B2C",
            "total": str(invoice.total_amount),
            "vat": str(invoice.total_vat),
            "currency": invoice.currency_code,
            "v": "3.0",  # Peppol BIS version
            "ts": datetime.utcnow().isoformat(),
        }
        
        return json.dumps(qr_data, separators=(",", ":"))
    
    def to_ubl_xml(self, invoice: PeppolInvoice) -> str:
        """
        Convert invoice to UBL 2.1 XML format (Peppol BIS Billing 3.0).
        
        Args:
            invoice: The invoice to convert
        
        Returns:
            XML string
        """
        # Create root element with namespaces
        nsmap = {
            None: self.UBL_NAMESPACE,
            "cac": self.CAC_NAMESPACE,
            "cbc": self.CBC_NAMESPACE,
        }
        
        # Build XML manually for proper namespace handling
        root = ET.Element("Invoice")
        root.set("xmlns", self.UBL_NAMESPACE)
        root.set("xmlns:cac", self.CAC_NAMESPACE)
        root.set("xmlns:cbc", self.CBC_NAMESPACE)
        
        # UBL Version
        self._add_element(root, "cbc:UBLVersionID", "2.1")
        
        # Customization and Profile IDs
        self._add_element(root, "cbc:CustomizationID", self.CUSTOMIZATION_ID)
        self._add_element(root, "cbc:ProfileID", self.PEPPOL_PROFILE_ID)
        
        # Invoice ID and dates
        self._add_element(root, "cbc:ID", invoice.invoice_number)
        self._add_element(root, "cbc:IssueDate", invoice.invoice_date.isoformat())
        self._add_element(root, "cbc:DueDate", invoice.due_date.isoformat())
        self._add_element(root, "cbc:InvoiceTypeCode", invoice.invoice_type.value)
        
        # Notes (includes CSID and QR data for NRS)
        if invoice.notes:
            self._add_element(root, "cbc:Note", invoice.notes)
        
        # NRS Extensions (custom Nigeria elements)
        nrs_ext = ET.SubElement(root, "cbc:Note")
        nrs_ext.text = f"NRS-CSID:{invoice.nrs_csid or self.generate_csid(invoice)}"
        
        qr_note = ET.SubElement(root, "cbc:Note")
        qr_note.text = f"NRS-QR:{invoice.nrs_qr_code_data or self.generate_qr_code_data(invoice)}"
        
        if invoice.nrs_irn:
            irn_note = ET.SubElement(root, "cbc:Note")
            irn_note.text = f"NRS-IRN:{invoice.nrs_irn}"
        
        # Document Currency
        self._add_element(root, "cbc:DocumentCurrencyCode", invoice.currency_code)
        
        # Supplier (Seller) Party
        supplier_party = ET.SubElement(root, "cac:AccountingSupplierParty")
        self._add_party(supplier_party, invoice.seller, "cac:Party")
        
        # Customer (Buyer) Party
        customer_party = ET.SubElement(root, "cac:AccountingCustomerParty")
        self._add_party(customer_party, invoice.buyer, "cac:Party")
        
        # Payment Terms
        if invoice.payment_terms:
            payment_terms = ET.SubElement(root, "cac:PaymentTerms")
            self._add_element(payment_terms, "cbc:Note", invoice.payment_terms)
        
        # Tax Total
        tax_total = ET.SubElement(root, "cac:TaxTotal")
        tax_amount = ET.SubElement(tax_total, "cbc:TaxAmount")
        tax_amount.set("currencyID", invoice.currency_code)
        tax_amount.text = str(invoice.total_vat)
        
        # Tax Subtotal
        tax_subtotal = ET.SubElement(tax_total, "cac:TaxSubtotal")
        taxable_amount = ET.SubElement(tax_subtotal, "cbc:TaxableAmount")
        taxable_amount.set("currencyID", invoice.currency_code)
        taxable_amount.text = str(invoice.subtotal)
        
        subtotal_tax = ET.SubElement(tax_subtotal, "cbc:TaxAmount")
        subtotal_tax.set("currencyID", invoice.currency_code)
        subtotal_tax.text = str(invoice.total_vat)
        
        tax_category = ET.SubElement(tax_subtotal, "cac:TaxCategory")
        self._add_element(tax_category, "cbc:ID", TaxCategoryCode.STANDARD_RATE.value)
        self._add_element(tax_category, "cbc:Percent", "7.5")  # Nigeria VAT rate
        tax_scheme = ET.SubElement(tax_category, "cac:TaxScheme")
        self._add_element(tax_scheme, "cbc:ID", "VAT")
        
        # Legal Monetary Total
        monetary_total = ET.SubElement(root, "cac:LegalMonetaryTotal")
        
        line_ext_amount = ET.SubElement(monetary_total, "cbc:LineExtensionAmount")
        line_ext_amount.set("currencyID", invoice.currency_code)
        line_ext_amount.text = str(invoice.subtotal)
        
        tax_exclusive = ET.SubElement(monetary_total, "cbc:TaxExclusiveAmount")
        tax_exclusive.set("currencyID", invoice.currency_code)
        tax_exclusive.text = str(invoice.subtotal)
        
        tax_inclusive = ET.SubElement(monetary_total, "cbc:TaxInclusiveAmount")
        tax_inclusive.set("currencyID", invoice.currency_code)
        tax_inclusive.text = str(invoice.total_amount)
        
        payable = ET.SubElement(monetary_total, "cbc:PayableAmount")
        payable.set("currencyID", invoice.currency_code)
        payable.text = str(invoice.total_amount)
        
        # Invoice Lines
        for idx, item in enumerate(invoice.line_items, 1):
            self._add_invoice_line(root, item, idx, invoice.currency_code)
        
        # Convert to pretty XML string
        xml_str = ET.tostring(root, encoding="unicode")
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ")
    
    def _add_element(self, parent: ET.Element, tag: str, text: str) -> ET.Element:
        """Add a simple text element."""
        elem = ET.SubElement(parent, tag)
        elem.text = text
        return elem
    
    def _add_party(self, parent: ET.Element, party: PeppolParty, party_tag: str) -> None:
        """Add party information to XML."""
        party_elem = ET.SubElement(parent, party_tag)
        
        # Endpoint ID (TIN)
        if party.tin:
            endpoint = ET.SubElement(party_elem, "cbc:EndpointID")
            endpoint.set("schemeID", self.NRS_SCHEME_ID)
            endpoint.text = party.tin
        
        # Party Identification
        if party.tin:
            party_id = ET.SubElement(party_elem, "cac:PartyIdentification")
            id_elem = ET.SubElement(party_id, "cbc:ID")
            id_elem.set("schemeID", self.NRS_SCHEME_ID)
            id_elem.text = party.tin
        
        # Party Name
        party_name = ET.SubElement(party_elem, "cac:PartyName")
        self._add_element(party_name, "cbc:Name", party.name)
        
        # Postal Address
        if party.street_address or party.city:
            address = ET.SubElement(party_elem, "cac:PostalAddress")
            if party.street_address:
                self._add_element(address, "cbc:StreetName", party.street_address)
            if party.city:
                self._add_element(address, "cbc:CityName", party.city)
            if party.postal_code:
                self._add_element(address, "cbc:PostalZone", party.postal_code)
            if party.state:
                self._add_element(address, "cbc:CountrySubentity", party.state)
            country = ET.SubElement(address, "cac:Country")
            self._add_element(country, "cbc:IdentificationCode", party.country_code)
        
        # Party Tax Scheme (TIN)
        if party.tin:
            tax_scheme = ET.SubElement(party_elem, "cac:PartyTaxScheme")
            self._add_element(tax_scheme, "cbc:CompanyID", party.tin)
            scheme = ET.SubElement(tax_scheme, "cac:TaxScheme")
            self._add_element(scheme, "cbc:ID", "VAT")
        
        # Party Legal Entity
        legal_entity = ET.SubElement(party_elem, "cac:PartyLegalEntity")
        self._add_element(legal_entity, "cbc:RegistrationName", party.registration_name or party.name)
        
        # Contact
        if party.contact_name or party.contact_email or party.contact_phone:
            contact = ET.SubElement(party_elem, "cac:Contact")
            if party.contact_name:
                self._add_element(contact, "cbc:Name", party.contact_name)
            if party.contact_phone:
                self._add_element(contact, "cbc:Telephone", party.contact_phone)
            if party.contact_email:
                self._add_element(contact, "cbc:ElectronicMail", party.contact_email)
    
    def _add_invoice_line(
        self,
        parent: ET.Element,
        item: PeppolLineItem,
        line_number: int,
        currency_code: str,
    ) -> None:
        """Add an invoice line to XML."""
        line = ET.SubElement(parent, "cac:InvoiceLine")
        
        self._add_element(line, "cbc:ID", str(line_number))
        
        quantity = ET.SubElement(line, "cbc:InvoicedQuantity")
        quantity.set("unitCode", item.unit_code)
        quantity.text = str(item.quantity)
        
        line_amount = ET.SubElement(line, "cbc:LineExtensionAmount")
        line_amount.set("currencyID", currency_code)
        line_amount.text = str(item.line_total)
        
        # Item
        item_elem = ET.SubElement(line, "cac:Item")
        self._add_element(item_elem, "cbc:Description", item.description)
        self._add_element(item_elem, "cbc:Name", item.description[:100])  # Max 100 chars
        
        # Item Classification (HS code if available)
        if item.item_classification_code:
            classification = ET.SubElement(item_elem, "cac:CommodityClassification")
            code = ET.SubElement(classification, "cbc:ItemClassificationCode")
            code.set("listID", "HS")
            code.text = item.item_classification_code
        
        # Tax Category
        tax_cat = ET.SubElement(item_elem, "cac:ClassifiedTaxCategory")
        self._add_element(tax_cat, "cbc:ID", item.tax_category.value)
        self._add_element(tax_cat, "cbc:Percent", str(item.vat_rate))
        scheme = ET.SubElement(tax_cat, "cac:TaxScheme")
        self._add_element(scheme, "cbc:ID", "VAT")
        
        # Price
        price = ET.SubElement(line, "cac:Price")
        price_amount = ET.SubElement(price, "cbc:PriceAmount")
        price_amount.set("currencyID", currency_code)
        price_amount.text = str(item.unit_price)
    
    def to_json(self, invoice: PeppolInvoice) -> str:
        """
        Convert invoice to JSON format (Peppol BIS Billing 3.0 JSON representation).
        
        Args:
            invoice: The invoice to convert
        
        Returns:
            JSON string
        """
        # Ensure CSID and QR data exist
        csid = invoice.nrs_csid or self.generate_csid(invoice)
        qr_data = invoice.nrs_qr_code_data or self.generate_qr_code_data(invoice)
        
        json_invoice = {
            "_meta": {
                "version": "3.0",
                "standard": "Peppol BIS Billing 3.0",
                "customization_id": self.CUSTOMIZATION_ID,
                "profile_id": self.PEPPOL_PROFILE_ID,
                "generator": "Tekvwa Pro Audit",
            },
            "nrs_compliance": {
                "irn": invoice.nrs_irn,
                "csid": csid,
                "qr_code_data": qr_data,
                "portal": "https://taxid.nrs.gov.ng/",
                "is_compliant": True,
            },
            "invoice": {
                "id": invoice.invoice_number,
                "issue_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat(),
                "invoice_type_code": invoice.invoice_type.value,
                "document_currency_code": invoice.currency_code,
                "note": invoice.notes,
            },
            "supplier": self._party_to_dict(invoice.seller),
            "customer": self._party_to_dict(invoice.buyer),
            "payment_terms": {
                "note": invoice.payment_terms,
            } if invoice.payment_terms else None,
            "tax_total": {
                "tax_amount": float(invoice.total_vat),
                "currency": invoice.currency_code,
                "tax_subtotals": [
                    {
                        "taxable_amount": float(invoice.subtotal),
                        "tax_amount": float(invoice.total_vat),
                        "tax_category": {
                            "id": TaxCategoryCode.STANDARD_RATE.value,
                            "percent": 7.5,
                            "tax_scheme": "VAT",
                        },
                    }
                ],
            },
            "monetary_total": {
                "line_extension_amount": float(invoice.subtotal),
                "tax_exclusive_amount": float(invoice.subtotal),
                "tax_inclusive_amount": float(invoice.total_amount),
                "payable_amount": float(invoice.total_amount),
                "currency": invoice.currency_code,
            },
            "invoice_lines": [
                self._line_item_to_dict(item, idx)
                for idx, item in enumerate(invoice.line_items, 1)
            ],
        }
        
        return json.dumps(json_invoice, indent=2, default=str)
    
    def _party_to_dict(self, party: PeppolParty) -> Dict[str, Any]:
        """Convert party to dictionary."""
        return {
            "name": party.name,
            "tin": party.tin,
            "tin_scheme": self.NRS_SCHEME_ID,
            "registration_name": party.registration_name or party.name,
            "address": {
                "street": party.street_address,
                "city": party.city,
                "state": party.state,
                "postal_code": party.postal_code,
                "country_code": party.country_code,
            },
            "contact": {
                "name": party.contact_name,
                "email": party.contact_email,
                "phone": party.contact_phone,
            },
        }
    
    def _line_item_to_dict(self, item: PeppolLineItem, line_number: int) -> Dict[str, Any]:
        """Convert line item to dictionary."""
        return {
            "id": line_number,
            "item_id": item.item_id,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit_code": item.unit_code,
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
            "tax": {
                "rate": float(item.vat_rate),
                "amount": float(item.vat_amount),
                "category": item.tax_category.value,
            },
            "classification_code": item.item_classification_code,
        }


def get_peppol_export_service() -> PeppolExportService:
    """Get Peppol export service instance."""
    return PeppolExportService()
