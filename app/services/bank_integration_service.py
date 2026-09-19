"""
Tekvwa Pro Audit - Bank Integration Service

Service for integrating with Nigerian banking APIs:
- Mono (https://mono.co) - Bank data aggregation
- Okra (https://okra.ng) - Open banking
- Stitch (https://stitch.money) - Payment integration

Also handles multi-channel import:
- CSV/Excel file parsing
- MT940/SWIFT format parsing
- PDF OCR (via Azure Form Recognizer)
"""

import csv
import hashlib
import io
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.bank_reconciliation import (
    BankAccount,
    BankStatement,
    BankStatementImport,
    BankStatementSource,
    BankStatementTransaction,
)

logger = logging.getLogger(__name__)


class BankIntegrationService:
    """
    Service for integrating with Nigerian banking APIs and handling
    multi-channel bank statement imports.
    """
    
    # Nigerian bank charge patterns for auto-detection
    EMTL_PATTERNS = [
        r"EMTL",
        r"E-LEVY",
        r"TRANSFER\s*LEVY",
        r"NIP\s*LEVY",
        r"ELECTRONIC\s*MONEY\s*TRANSFER\s*LEVY",
    ]
    
    STAMP_DUTY_PATTERNS = [
        r"STAMP\s*DUTY",
        r"STD",
        r"STAMP\s*DTY",
    ]
    
    BANK_CHARGE_PATTERNS = [
        r"SMS\s*ALERT",
        r"SMS\s*CHG",
        r"SMS\s*FEE",
        r"MAINTENANCE",
        r"COT",
        r"ACCOUNT\s*FEE",
        r"CHARGES",
        r"COMMISSION",
        r"ATM\s*CHARGES",
        r"CARD\s*MAINTENANCE",
    ]
    
    VAT_PATTERNS = [
        r"\bVAT\b",
        r"V\.A\.T",
        r"VALUE\s*ADDED\s*TAX",
    ]
    
    WHT_PATTERNS = [
        r"\bWHT\b",
        r"WITHHOLDING\s*TAX",
        r"W/TAX",
    ]
    
    POS_PATTERNS = [
        r"\bPOS\b",
        r"POINT\s*OF\s*SALE",
        r"POS\s*SETTLEMENT",
        r"MERCHANT\s*SETTLEMENT",
    ]
    
    NIP_PATTERNS = [
        r"\bNIP\b",
        r"NIBSS\s*INSTANT",
        r"INSTANT\s*PAYMENT",
        r"NIP\s*TRANSFER",
    ]
    
    USSD_PATTERNS = [
        r"\bUSSD\b",
        r"\*\d{3}#",
        r"MOBILE\s*BANKING",
    ]
    
    REVERSAL_PATTERNS = [
        r"REVERSAL",
        r"REVERSED",
        r"REV\b",
        r"REFUND",
        r"CANCELLED",
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._mono_client = None
        self._okra_client = None
        self._stitch_client = None
    
    # ===========================================
    # MONO API INTEGRATION
    # https://docs.mono.co/
    # ===========================================
    
    async def _get_mono_client(self) -> httpx.AsyncClient:
        """Get or create Mono API client."""
        if self._mono_client is None:
            self._mono_client = httpx.AsyncClient(
                base_url=settings.mono_active_url,
                headers={
                    "mono-sec-key": settings.mono_active_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._mono_client
    
    async def mono_exchange_token(self, auth_code: str) -> Dict[str, Any]:
        """
        Exchange Mono Connect widget auth code for account ID.
        
        Args:
            auth_code: Authorization code from Mono Connect widget
            
        Returns:
            Dict with account_id
        """
        client = await self._get_mono_client()
        
        try:
            response = await client.post(
                "/account/auth",
                json={"code": auth_code},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Mono auth exchange failed: {e}")
            raise
    
    async def mono_get_account_details(self, account_id: str) -> Dict[str, Any]:
        """
        Get account details from Mono.
        
        Args:
            account_id: Mono account ID
            
        Returns:
            Account details including bank name, account number, balance
        """
        client = await self._get_mono_client()
        
        try:
            response = await client.get(f"/accounts/{account_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Mono get account failed: {e}")
            raise
    
    async def mono_get_transactions(
        self,
        account_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        paginate: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transactions from Mono.
        
        Args:
            account_id: Mono account ID
            start_date: Start date for transaction range
            end_date: End date for transaction range
            paginate: Whether to paginate through all results
            
        Returns:
            List of transactions
        """
        client = await self._get_mono_client()
        
        params = {}
        if start_date:
            params["start"] = start_date.strftime("%d-%m-%Y")
        if end_date:
            params["end"] = end_date.strftime("%d-%m-%Y")
        
        all_transactions = []
        page = 1
        
        try:
            while True:
                params["page"] = page
                response = await client.get(
                    f"/accounts/{account_id}/transactions",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
                
                transactions = data.get("data", [])
                all_transactions.extend(transactions)
                
                if not paginate or len(transactions) < 20:  # Mono default page size
                    break
                    
                page += 1
                
            return all_transactions
        except httpx.HTTPError as e:
            logger.error(f"Mono get transactions failed: {e}")
            raise
    
    async def mono_sync_bank_account(
        self,
        bank_account_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> BankStatementImport:
        """
        Sync transactions from Mono to local database.
        
        Args:
            bank_account_id: Local bank account ID
            start_date: Start date for sync
            end_date: End date for sync
            
        Returns:
            BankStatementImport record with sync results
        """
        # Get bank account
        result = await self.db.execute(
            select(BankAccount).where(BankAccount.id == bank_account_id)
        )
        bank_account = result.scalar_one_or_none()
        
        if not bank_account or not bank_account.mono_account_id:
            raise ValueError("Bank account not connected to Mono")
        
        # Create import record
        import_record = BankStatementImport(
            entity_id=bank_account.entity_id,
            bank_account_id=bank_account_id,
            source=BankStatementSource.MONO_API,
            statement_start_date=start_date,
            statement_end_date=end_date,
            status="processing",
        )
        self.db.add(import_record)
        await self.db.flush()
        
        start_time = datetime.utcnow()
        
        try:
            # Fetch transactions from Mono
            transactions = await self.mono_get_transactions(
                bank_account.mono_account_id,
                start_date,
                end_date,
            )
            
            import_record.total_rows = len(transactions)
            
            # Process transactions
            imported = 0
            duplicates = 0
            errors = 0
            
            for txn in transactions:
                try:
                    # Check for duplicate
                    external_id = txn.get("_id")
                    if external_id:
                        existing = await self.db.execute(
                            select(BankStatementTransaction).where(
                                BankStatementTransaction.bank_account_id == bank_account_id,
                                BankStatementTransaction.external_id == external_id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            duplicates += 1
                            continue
                    
                    # Parse and create transaction
                    bank_txn = self._parse_mono_transaction(
                        txn, bank_account_id, import_record.id
                    )
                    self.db.add(bank_txn)
                    imported += 1
                    
                except Exception as e:
                    logger.error(f"Error processing Mono transaction: {e}")
                    errors += 1
            
            # Update import record
            import_record.imported_count = imported
            import_record.duplicate_count = duplicates
            import_record.error_count = errors
            import_record.status = "completed"
            
            # Update bank account sync status
            bank_account.mono_last_sync = datetime.utcnow()
            bank_account.last_sync_status = "success"
            
        except Exception as e:
            import_record.status = "failed"
            import_record.error_message = str(e)
            bank_account.last_sync_status = "failed"
            bank_account.last_sync_error = str(e)
            raise
        finally:
            import_record.processing_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            await self.db.commit()
        
        return import_record
    
    def _parse_mono_transaction(
        self,
        txn: Dict[str, Any],
        bank_account_id: UUID,
        import_id: Optional[UUID] = None,
    ) -> BankStatementTransaction:
        """Parse Mono transaction into BankStatementTransaction model."""
        
        narration = txn.get("narration", "")
        amount = Decimal(str(txn.get("amount", 0))) / 100  # Mono uses kobo
        
        # Determine debit/credit
        txn_type = txn.get("type", "").lower()
        debit_amount = amount if txn_type == "debit" else None
        credit_amount = amount if txn_type == "credit" else None
        
        # Parse date
        txn_date = datetime.fromisoformat(
            txn.get("date", "").replace("Z", "+00:00")
        ).date()
        
        # Detect Nigerian charges
        charge_flags = self._detect_nigerian_charges(narration, amount)
        
        # Generate duplicate hash
        dup_hash = self._generate_transaction_hash(
            txn_date, narration, debit_amount, credit_amount
        )
        
        return BankStatementTransaction(
            bank_account_id=bank_account_id,
            transaction_date=txn_date,
            value_date=txn_date,
            raw_narration=narration,
            clean_narration=self._clean_narration(narration),
            narration=narration,
            reference=txn.get("_id"),
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            balance=Decimal(str(txn.get("balance", 0))) / 100 if txn.get("balance") else None,
            transaction_type=txn.get("type"),
            category=txn.get("category"),
            external_id=txn.get("_id"),
            source=BankStatementSource.MONO_API,
            duplicate_hash=dup_hash,
            raw_data=txn,
            **charge_flags,
        )
    
    # ===========================================
    # OKRA API INTEGRATION
    # https://docs.okra.ng/
    # ===========================================
    
    async def _get_okra_client(self) -> httpx.AsyncClient:
        """Get or create Okra API client."""
        if self._okra_client is None:
            self._okra_client = httpx.AsyncClient(
                base_url=settings.okra_active_url,
                headers={
                    "Authorization": f"Bearer {settings.okra_active_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._okra_client
    
    async def okra_get_transactions(
        self,
        account_id: str,
        record_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch transactions from Okra.
        
        Args:
            account_id: Okra account ID
            record_id: Okra record ID
            start_date: Start date for transaction range
            end_date: End date for transaction range
            
        Returns:
            List of transactions
        """
        client = await self._get_okra_client()
        
        payload = {
            "account": account_id,
            "record": record_id,
        }
        
        if start_date:
            payload["from"] = start_date.isoformat()
        if end_date:
            payload["to"] = end_date.isoformat()
        
        try:
            response = await client.post(
                "/transactions/getByAccount",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("transaction", [])
        except httpx.HTTPError as e:
            logger.error(f"Okra get transactions failed: {e}")
            raise
    
    async def okra_sync_bank_account(
        self,
        bank_account_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> BankStatementImport:
        """Sync transactions from Okra to local database."""
        
        result = await self.db.execute(
            select(BankAccount).where(BankAccount.id == bank_account_id)
        )
        bank_account = result.scalar_one_or_none()
        
        if not bank_account or not bank_account.okra_account_id:
            raise ValueError("Bank account not connected to Okra")
        
        import_record = BankStatementImport(
            entity_id=bank_account.entity_id,
            bank_account_id=bank_account_id,
            source=BankStatementSource.OKRA_API,
            statement_start_date=start_date,
            statement_end_date=end_date,
            status="processing",
        )
        self.db.add(import_record)
        await self.db.flush()
        
        start_time = datetime.utcnow()
        
        try:
            transactions = await self.okra_get_transactions(
                bank_account.okra_account_id,
                bank_account.okra_record_id,
                start_date,
                end_date,
            )
            
            import_record.total_rows = len(transactions)
            
            imported = 0
            duplicates = 0
            errors = 0
            
            for txn in transactions:
                try:
                    external_id = txn.get("_id")
                    if external_id:
                        existing = await self.db.execute(
                            select(BankStatementTransaction).where(
                                BankStatementTransaction.bank_account_id == bank_account_id,
                                BankStatementTransaction.external_id == external_id,
                            )
                        )
                        if existing.scalar_one_or_none():
                            duplicates += 1
                            continue
                    
                    bank_txn = self._parse_okra_transaction(
                        txn, bank_account_id, import_record.id
                    )
                    self.db.add(bank_txn)
                    imported += 1
                    
                except Exception as e:
                    logger.error(f"Error processing Okra transaction: {e}")
                    errors += 1
            
            import_record.imported_count = imported
            import_record.duplicate_count = duplicates
            import_record.error_count = errors
            import_record.status = "completed"
            
            bank_account.okra_last_sync = datetime.utcnow()
            bank_account.last_sync_status = "success"
            
        except Exception as e:
            import_record.status = "failed"
            import_record.error_message = str(e)
            bank_account.last_sync_status = "failed"
            bank_account.last_sync_error = str(e)
            raise
        finally:
            import_record.processing_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            await self.db.commit()
        
        return import_record
    
    def _parse_okra_transaction(
        self,
        txn: Dict[str, Any],
        bank_account_id: UUID,
        import_id: Optional[UUID] = None,
    ) -> BankStatementTransaction:
        """Parse Okra transaction into BankStatementTransaction model."""
        
        narration = txn.get("notes", {}).get("desc", "") or txn.get("trans_date", "")
        
        # Okra stores amounts as negative for debits
        amount = Decimal(str(abs(txn.get("amount", 0))))
        is_debit = txn.get("type") == "debit" or txn.get("amount", 0) < 0
        
        debit_amount = amount if is_debit else None
        credit_amount = amount if not is_debit else None
        
        txn_date = datetime.fromisoformat(
            txn.get("trans_date", "").replace("Z", "+00:00")
        ).date()
        
        charge_flags = self._detect_nigerian_charges(narration, amount)
        dup_hash = self._generate_transaction_hash(
            txn_date, narration, debit_amount, credit_amount
        )
        
        return BankStatementTransaction(
            bank_account_id=bank_account_id,
            transaction_date=txn_date,
            value_date=txn_date,
            raw_narration=narration,
            clean_narration=self._clean_narration(narration),
            narration=narration,
            reference=txn.get("_id"),
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            balance=Decimal(str(txn.get("cleared_balance", 0))) if txn.get("cleared_balance") else None,
            transaction_type=txn.get("type"),
            external_id=txn.get("_id"),
            source=BankStatementSource.OKRA_API,
            duplicate_hash=dup_hash,
            raw_data=txn,
            **charge_flags,
        )
    
    # ===========================================
    # CSV/EXCEL IMPORT
    # ===========================================
    
    async def import_csv_statement(
        self,
        bank_account_id: UUID,
        entity_id: UUID,
        file_content: bytes,
        filename: str,
        column_mapping: Dict[str, str],
        date_format: str = "%d/%m/%Y",
        skip_rows: int = 0,
        has_header: bool = True,
    ) -> BankStatementImport:
        """
        Import bank statement from CSV file.
        
        Args:
            bank_account_id: Target bank account ID
            entity_id: Entity ID
            file_content: CSV file content as bytes
            filename: Original filename
            column_mapping: Mapping of CSV columns to fields
            date_format: Date format string
            skip_rows: Number of rows to skip at start
            has_header: Whether CSV has header row
            
        Returns:
            BankStatementImport record with import results
        """
        # Generate file hash for duplicate detection
        file_hash = hashlib.sha256(file_content).hexdigest()
        
        # Check for duplicate import
        existing = await self.db.execute(
            select(BankStatementImport).where(
                BankStatementImport.bank_account_id == bank_account_id,
                BankStatementImport.file_hash == file_hash,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("This file has already been imported")
        
        import_record = BankStatementImport(
            entity_id=entity_id,
            bank_account_id=bank_account_id,
            source=BankStatementSource.CSV_UPLOAD,
            filename=filename,
            file_hash=file_hash,
            status="processing",
        )
        self.db.add(import_record)
        await self.db.flush()
        
        start_time = datetime.utcnow()
        
        try:
            # Parse CSV
            content_str = file_content.decode("utf-8-sig")  # Handle BOM
            reader = csv.DictReader(io.StringIO(content_str))
            
            rows = list(reader)
            import_record.total_rows = len(rows)
            
            imported = 0
            duplicates = 0
            errors = 0
            min_date = None
            max_date = None
            
            for row in rows[skip_rows:]:
                try:
                    # Parse transaction from row
                    bank_txn = self._parse_csv_row(
                        row, bank_account_id, column_mapping, date_format
                    )
                    
                    # Check for duplicate
                    existing = await self.db.execute(
                        select(BankStatementTransaction).where(
                            BankStatementTransaction.duplicate_hash == bank_txn.duplicate_hash
                        )
                    )
                    if existing.scalar_one_or_none():
                        duplicates += 1
                        continue
                    
                    self.db.add(bank_txn)
                    imported += 1
                    
                    # Track date range
                    if min_date is None or bank_txn.transaction_date < min_date:
                        min_date = bank_txn.transaction_date
                    if max_date is None or bank_txn.transaction_date > max_date:
                        max_date = bank_txn.transaction_date
                        
                except Exception as e:
                    logger.error(f"Error processing CSV row: {e}")
                    errors += 1
            
            import_record.imported_count = imported
            import_record.duplicate_count = duplicates
            import_record.error_count = errors
            import_record.statement_start_date = min_date
            import_record.statement_end_date = max_date
            import_record.status = "completed"
            
        except Exception as e:
            import_record.status = "failed"
            import_record.error_message = str(e)
            raise
        finally:
            import_record.processing_time_ms = int(
                (datetime.utcnow() - start_time).total_seconds() * 1000
            )
            await self.db.commit()
        
        return import_record
    
    def _parse_csv_row(
        self,
        row: Dict[str, str],
        bank_account_id: UUID,
        column_mapping: Dict[str, str],
        date_format: str,
    ) -> BankStatementTransaction:
        """Parse a CSV row into BankStatementTransaction."""
        
        # Get mapped values
        date_str = row.get(column_mapping.get("date_column", ""), "").strip()
        narration = row.get(column_mapping.get("narration_column", ""), "").strip()
        
        # Parse date
        txn_date = datetime.strptime(date_str, date_format).date()
        
        # Parse amounts
        debit_amount = None
        credit_amount = None
        
        if "amount_column" in column_mapping:
            # Single amount column (negative = debit)
            amount_str = row.get(column_mapping["amount_column"], "").strip()
            amount = self._parse_amount(amount_str)
            if amount < 0:
                debit_amount = abs(amount)
            else:
                credit_amount = amount
        else:
            # Separate debit/credit columns
            debit_str = row.get(column_mapping.get("debit_column", ""), "").strip()
            credit_str = row.get(column_mapping.get("credit_column", ""), "").strip()
            
            if debit_str:
                debit_amount = self._parse_amount(debit_str)
            if credit_str:
                credit_amount = self._parse_amount(credit_str)
        
        # Parse balance
        balance = None
        if "balance_column" in column_mapping:
            balance_str = row.get(column_mapping["balance_column"], "").strip()
            if balance_str:
                balance = self._parse_amount(balance_str)
        
        # Get reference
        reference = None
        if "reference_column" in column_mapping:
            reference = row.get(column_mapping["reference_column"], "").strip()
        
        # Detect Nigerian charges
        amount = debit_amount or credit_amount or Decimal("0")
        charge_flags = self._detect_nigerian_charges(narration, amount)
        
        # Generate duplicate hash
        dup_hash = self._generate_transaction_hash(
            txn_date, narration, debit_amount, credit_amount
        )
        
        return BankStatementTransaction(
            bank_account_id=bank_account_id,
            transaction_date=txn_date,
            raw_narration=narration,
            clean_narration=self._clean_narration(narration),
            narration=narration,
            reference=reference,
            debit_amount=debit_amount,
            credit_amount=credit_amount,
            balance=balance,
            source=BankStatementSource.CSV_UPLOAD,
            duplicate_hash=dup_hash,
            **charge_flags,
        )
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse amount string to Decimal, handling various formats."""
        if not amount_str:
            return Decimal("0")
        
        # Remove currency symbols and spaces
        cleaned = re.sub(r"[^\d.,\-]", "", amount_str)
        
        # Handle European format (1.234,56) vs US format (1,234.56)
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                # European format
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # US format
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Could be decimal comma or thousand separator
            parts = cleaned.split(",")
            if len(parts[-1]) == 2:
                # Decimal comma
                cleaned = cleaned.replace(",", ".")
            else:
                # Thousand separator
                cleaned = cleaned.replace(",", "")
        
        return Decimal(cleaned)
    
    # ===========================================
    # NIGERIAN CHARGE DETECTION
    # ===========================================
    
    def _detect_nigerian_charges(
        self, narration: str, amount: Decimal
    ) -> Dict[str, Any]:
        """
        Detect Nigerian-specific charges from transaction narration.
        
        Returns dict with is_* flags and detected_charge_type.
        """
        narration_upper = narration.upper()
        
        flags = {
            "is_emtl": False,
            "is_stamp_duty": False,
            "is_bank_charge": False,
            "is_vat_charge": False,
            "is_wht_deduction": False,
            "is_pos_settlement": False,
            "is_nip_transfer": False,
            "is_ussd_transaction": False,
            "is_reversal": False,
            "detected_charge_type": None,
        }
        
        # Check EMTL (N50 exactly on inflows)
        if amount == Decimal("50") and any(
            re.search(p, narration_upper) for p in self.EMTL_PATTERNS
        ):
            flags["is_emtl"] = True
            flags["detected_charge_type"] = "emtl"
        
        # Check Stamp Duty (N50 exactly)
        elif amount == Decimal("50") and any(
            re.search(p, narration_upper) for p in self.STAMP_DUTY_PATTERNS
        ):
            flags["is_stamp_duty"] = True
            flags["detected_charge_type"] = "stamp_duty"
        
        # Check VAT
        elif any(re.search(p, narration_upper) for p in self.VAT_PATTERNS):
            flags["is_vat_charge"] = True
            flags["detected_charge_type"] = "vat_on_charges"
        
        # Check WHT
        elif any(re.search(p, narration_upper) for p in self.WHT_PATTERNS):
            flags["is_wht_deduction"] = True
            flags["detected_charge_type"] = "wht_deduction"
        
        # Check Bank Charges
        elif any(re.search(p, narration_upper) for p in self.BANK_CHARGE_PATTERNS):
            flags["is_bank_charge"] = True
            flags["detected_charge_type"] = "bank_charge"
        
        # Check POS
        if any(re.search(p, narration_upper) for p in self.POS_PATTERNS):
            flags["is_pos_settlement"] = True
        
        # Check NIP
        if any(re.search(p, narration_upper) for p in self.NIP_PATTERNS):
            flags["is_nip_transfer"] = True
        
        # Check USSD
        if any(re.search(p, narration_upper) for p in self.USSD_PATTERNS):
            flags["is_ussd_transaction"] = True
        
        # Check Reversal
        if any(re.search(p, narration_upper) for p in self.REVERSAL_PATTERNS):
            flags["is_reversal"] = True
        
        return flags
    
    def _clean_narration(self, narration: str) -> str:
        """Clean up narration for better matching."""
        if not narration:
            return ""
        
        # Remove extra whitespace
        cleaned = " ".join(narration.split())
        
        # Remove common prefixes
        prefixes_to_remove = [
            "TRANSFER FROM",
            "TRANSFER TO",
            "NIP TRANSFER TO",
            "NIP TRANSFER FROM",
            "WEB TRANSFER TO",
            "WEB TRANSFER FROM",
            "MOBILE TRANSFER TO",
            "MOBILE TRANSFER FROM",
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.upper().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned
    
    def _generate_transaction_hash(
        self,
        txn_date: date,
        narration: str,
        debit_amount: Optional[Decimal],
        credit_amount: Optional[Decimal],
    ) -> str:
        """Generate hash for duplicate detection."""
        amount = debit_amount or credit_amount or Decimal("0")
        data = f"{txn_date.isoformat()}|{narration}|{amount}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    # ===========================================
    # CLEANUP
    # ===========================================
    
    async def close(self):
        """Close API clients."""
        if self._mono_client:
            await self._mono_client.aclose()
        if self._okra_client:
            await self._okra_client.aclose()
        if self._stitch_client:
            await self._stitch_client.aclose()


async def get_bank_integration_service(db: AsyncSession) -> BankIntegrationService:
    """Dependency injection for BankIntegrationService."""
    return BankIntegrationService(db)
