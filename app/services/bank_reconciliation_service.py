"""
Tekvwa Pro Audit - Bank Reconciliation Service

Comprehensive service for Nigerian bank reconciliation operations.
Features:
- Bank account CRUD with Mono/Okra/Stitch integration
- Statement import and parsing (CSV, API)
- Nigerian-specific charge detection (EMTL, Stamp Duty, VAT, WHT)
- Auto-matching using fuzzy logic and rule-based matching
- Manual matching with confidence scoring
- One-to-many and many-to-one matching
- Reconciliation workflow (draft → in_review → approved/rejected → completed)
- Adjustment management with posting capability
- Unmatched item tracking and resolution
- Comprehensive reporting
"""

import uuid
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any, Tuple, Set
from difflib import SequenceMatcher

from sqlalchemy import select, and_, or_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bank_reconciliation import (
    BankAccount, BankAccountType, BankAccountCurrency, BankStatementSource,
    BankStatementTransaction, BankReconciliation, ReconciliationAdjustment,
    UnmatchedItem, BankChargeRule, MatchingRule, BankStatementImport,
    MatchStatus, ReconciliationStatus, MatchType, MatchConfidenceLevel,
    AdjustmentType, UnmatchedItemType, ChargeDetectionMethod,
)
from app.models.transaction import Transaction
from app.services.matching_engine import MatchingEngine, MatchingConfig


class BankReconciliationService:
    """
    Comprehensive service for Nigerian bank reconciliation operations.
    
    This service provides:
    - Bank account management with API integrations
    - Statement import from multiple sources
    - Nigerian-specific charge detection and classification
    - Intelligent transaction matching
    - Reconciliation workflow management
    - Adjustment tracking and posting
    - Comprehensive reporting
    """
    
    # Nigerian charge detection patterns
    NIGERIAN_CHARGE_PATTERNS = {
        'emtl': [
            r'emtl',
            r'electronic money transfer levy',
            r'e-?levy',
        ],
        'stamp_duty': [
            r'stamp\s*duty',
            r'sd\s*charges?',
            r'sd\s*fee',
        ],
        'sms_fee': [
            r'sms\s*(alert\s*)?(fee|charge)',
            r'sms\s*notification',
            r'alert\s*charge',
        ],
        'vat': [
            r'\bvat\b',
            r'value\s*added\s*tax',
            r'withholding\s*tax\s*on\s*vat',
        ],
        'wht': [
            r'\bwht\b',
            r'withholding\s*tax',
            r'w/?h\s*tax',
        ],
        'maintenance_fee': [
            r'maintenance\s*(fee|charge)',
            r'cot',
            r'commission\s*on\s*turnover',
            r'account\s*maintenance',
        ],
        'pos_fee': [
            r'pos\s*(fee|charge)',
            r'card\s*(transaction\s*)?(fee|charge)',
        ],
        'transfer_fee': [
            r'nip\s*(fee|charge)',
            r'transfer\s*(fee|charge)',
            r'nibss',
        ],
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._matching_engine = None
    
    @property
    def matching_engine(self) -> MatchingEngine:
        """Lazy-loaded matching engine."""
        if self._matching_engine is None:
            self._matching_engine = MatchingEngine(self.db)
        return self._matching_engine
    
    # ===========================================
    # BANK ACCOUNT OPERATIONS
    # ===========================================
    
    async def create_bank_account(
        self,
        entity_id: uuid.UUID,
        bank_name: str,
        account_name: str,
        account_number: str,
        account_type: BankAccountType = BankAccountType.CURRENT,
        currency: BankAccountCurrency = BankAccountCurrency.NGN,
        opening_balance: Decimal = Decimal("0.00"),
        opening_balance_date: Optional[date] = None,
        gl_account_code: Optional[str] = None,
        gl_account_name: Optional[str] = None,
        bank_code: Optional[str] = None,
        sort_code: Optional[str] = None,
        swift_code: Optional[str] = None,
        iban: Optional[str] = None,
        branch_name: Optional[str] = None,
        branch_address: Optional[str] = None,
        is_primary: bool = False,
        notes: Optional[str] = None,
        created_by_id: Optional[uuid.UUID] = None,
        # API integration fields
        mono_account_id: Optional[str] = None,
        okra_account_id: Optional[str] = None,
        stitch_account_id: Optional[str] = None,
    ) -> BankAccount:
        """
        Create a new bank account for reconciliation.

        Supports Nigerian banks with optional API integrations (Mono, Okra, Stitch).
        """
        account = BankAccount(
            entity_id=entity_id,
            bank_name=bank_name,
            account_name=account_name,
            account_number=account_number,
            account_type=account_type,
            currency=currency,
            opening_balance=opening_balance,
            opening_balance_date=opening_balance_date or date.today(),
            current_balance=opening_balance,
            gl_account_code=gl_account_code,
            gl_account_name=gl_account_name,
            bank_code=bank_code,
            sort_code=sort_code,
            swift_code=swift_code,
            iban=iban,
            branch_name=branch_name,
            branch_address=branch_address,
            is_primary=is_primary,
            notes=notes,
            created_by_id=created_by_id,
            mono_account_id=mono_account_id,
            okra_account_id=okra_account_id,
            stitch_account_id=stitch_account_id,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account
    
    async def get_bank_accounts(
        self,
        entity_id: uuid.UUID,
        is_active: Optional[bool] = True,
    ) -> List[BankAccount]:
        """Get all bank accounts for an entity."""
        query = select(BankAccount).where(BankAccount.entity_id == entity_id)
        if is_active is not None:
            query = query.where(BankAccount.is_active == is_active)
        query = query.order_by(BankAccount.bank_name, BankAccount.account_name)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def get_bank_account(
        self,
        account_id: uuid.UUID,
        entity_id: Optional[uuid.UUID] = None,
    ) -> Optional[BankAccount]:
        """Get a specific bank account by ID."""
        query = select(BankAccount).where(BankAccount.id == account_id)
        if entity_id:
            query = query.where(BankAccount.entity_id == entity_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def update_bank_account(
        self,
        account_id: uuid.UUID,
        **updates,
    ) -> Optional[BankAccount]:
        """Update a bank account."""
        account = await self.get_bank_account(account_id)
        if not account:
            return None
        
        for key, value in updates.items():
            if hasattr(account, key):
                setattr(account, key, value)
        
        await self.db.commit()
        await self.db.refresh(account)
        return account
    
    async def validate_gl_linkage(
        self,
        account_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Validate that a bank account is properly linked to a GL account.
        
        Returns validation result with details about GL linkage status.
        """
        from app.models.accounting import ChartOfAccounts
        
        account = await self.get_bank_account(account_id, entity_id)
        if not account:
            return {
                "valid": False,
                "error": "Bank account not found",
                "has_gl_code": False,
                "gl_account_exists": False,
            }
        
        if not account.gl_account_code:
            return {
                "valid": False,
                "error": "Bank account has no GL account linked",
                "has_gl_code": False,
                "gl_account_exists": False,
                "bank_account_id": str(account_id),
                "bank_account_name": account.account_name,
                "recommendation": "Link this bank account to a GL account (typically under 1120 - Bank)",
            }
        
        # Check if GL account exists
        result = await self.db.execute(
            select(ChartOfAccounts)
            .where(ChartOfAccounts.entity_id == entity_id)
            .where(ChartOfAccounts.account_code == account.gl_account_code)
            .where(ChartOfAccounts.is_active == True)
        )
        gl_account = result.scalar_one_or_none()
        
        if not gl_account:
            return {
                "valid": False,
                "error": f"GL account {account.gl_account_code} not found in Chart of Accounts",
                "has_gl_code": True,
                "gl_account_exists": False,
                "bank_account_id": str(account_id),
                "gl_account_code": account.gl_account_code,
                "recommendation": f"Create GL account {account.gl_account_code} or update bank account with valid GL code",
            }
        
        return {
            "valid": True,
            "has_gl_code": True,
            "gl_account_exists": True,
            "bank_account_id": str(account_id),
            "bank_account_name": account.account_name,
            "gl_account_id": str(gl_account.id),
            "gl_account_code": gl_account.account_code,
            "gl_account_name": gl_account.account_name,
        }
    
    async def validate_all_bank_gl_linkages(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Validate GL linkage for all bank accounts of an entity.
        
        Returns:
            Summary of validation results with list of issues.
        """
        accounts = await self.get_bank_accounts(entity_id, is_active=True)
        
        results = {
            "total_accounts": len(accounts),
            "linked_accounts": 0,
            "unlinked_accounts": 0,
            "invalid_linkages": 0,
            "accounts": [],
            "issues": [],
        }
        
        for account in accounts:
            validation = await self.validate_gl_linkage(account.id, entity_id)
            results["accounts"].append({
                "bank_account_id": str(account.id),
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "account_name": account.account_name,
                "gl_account_code": account.gl_account_code,
                "validation": validation,
            })
            
            if validation.get("valid"):
                results["linked_accounts"] += 1
            elif not validation.get("has_gl_code"):
                results["unlinked_accounts"] += 1
                results["issues"].append({
                    "type": "unlinked",
                    "bank_account_id": str(account.id),
                    "bank_account_name": account.account_name,
                    "message": validation.get("error"),
                    "recommendation": validation.get("recommendation"),
                })
            else:
                results["invalid_linkages"] += 1
                results["issues"].append({
                    "type": "invalid_gl_code",
                    "bank_account_id": str(account.id),
                    "bank_account_name": account.account_name,
                    "gl_account_code": account.gl_account_code,
                    "message": validation.get("error"),
                    "recommendation": validation.get("recommendation"),
                })
        
        results["all_valid"] = results["unlinked_accounts"] == 0 and results["invalid_linkages"] == 0
        
        return results
    
    async def link_bank_to_gl(
        self,
        bank_account_id: uuid.UUID,
        gl_account_code: str,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Link a bank account to a GL account.
        
        Validates the GL account exists before linking.
        """
        from app.models.accounting import ChartOfAccounts
        
        # Validate GL account exists
        result = await self.db.execute(
            select(ChartOfAccounts)
            .where(ChartOfAccounts.entity_id == entity_id)
            .where(ChartOfAccounts.account_code == gl_account_code)
            .where(ChartOfAccounts.is_active == True)
        )
        gl_account = result.scalar_one_or_none()
        
        if not gl_account:
            return {
                "success": False,
                "error": f"GL account {gl_account_code} not found in Chart of Accounts",
            }
        
        # Update bank account
        account = await self.update_bank_account(
            bank_account_id,
            gl_account_code=gl_account_code,
            gl_account_name=gl_account.account_name,
        )
        
        if not account:
            return {
                "success": False,
                "error": "Bank account not found",
            }
        
        return {
            "success": True,
            "bank_account_id": str(bank_account_id),
            "gl_account_id": str(gl_account.id),
            "gl_account_code": gl_account_code,
            "gl_account_name": gl_account.account_name,
        }
    
    async def get_gl_account_id_for_bank(
        self,
        bank_account_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> Optional[uuid.UUID]:
        """
        Get the GL account ID linked to a bank account.
        
        Returns None if no valid linkage exists.
        """
        from app.models.accounting import ChartOfAccounts
        
        account = await self.get_bank_account(bank_account_id, entity_id)
        if not account or not account.gl_account_code:
            return None
        
        result = await self.db.execute(
            select(ChartOfAccounts.id)
            .where(ChartOfAccounts.entity_id == entity_id)
            .where(ChartOfAccounts.account_code == account.gl_account_code)
            .where(ChartOfAccounts.is_active == True)
        )
        return result.scalar_one_or_none()
    
    # ===========================================
    # STATEMENT IMPORT
    # ===========================================
    
    async def create_statement_import(
        self,
        bank_account_id: uuid.UUID,
        source: BankStatementSource,
        period_start: date,
        period_end: date,
        imported_by_id: Optional[uuid.UUID] = None,
        file_name: Optional[str] = None,
        file_size: Optional[int] = None,
        file_hash: Optional[str] = None,
        api_request_id: Optional[str] = None,
    ) -> BankStatementImport:
        """Create a statement import record for tracking."""
        import_record = BankStatementImport(
            bank_account_id=bank_account_id,
            source=source,
            period_start=period_start,
            period_end=period_end,
            imported_by_id=imported_by_id,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
            api_request_id=api_request_id,
            status="processing",
        )
        self.db.add(import_record)
        await self.db.commit()
        await self.db.refresh(import_record)
        return import_record
    
    async def import_statement_transactions(
        self,
        bank_account_id: uuid.UUID,
        reconciliation_id: Optional[uuid.UUID],
        transactions: List[Dict[str, Any]],
        source: BankStatementSource = BankStatementSource.MANUAL_ENTRY,
        import_id: Optional[uuid.UUID] = None,
        auto_detect_charges: bool = True,
    ) -> Dict[str, Any]:
        """
        Import bank statement transactions with Nigerian charge auto-detection.
        
        Args:
            bank_account_id: The bank account to import to
            reconciliation_id: Optional reconciliation to link transactions to
            transactions: List of transaction dicts with keys:
                - transaction_date: date
                - description: str
                - debit_amount: Decimal (optional)
                - credit_amount: Decimal (optional)
                - balance: Decimal (optional)
                - reference: str (optional)
                - value_date: date (optional)
                - bank_reference: str (optional)
            source: Source of the statement data
            import_id: Optional import record ID for tracking
            auto_detect_charges: Whether to auto-detect Nigerian bank charges
            
        Returns:
            Dict with import statistics
        """
        imported_count = 0
        charge_count = 0
        duplicate_count = 0
        
        for txn_data in transactions:
            # Check for duplicates
            existing = await self._check_duplicate_transaction(
                bank_account_id,
                txn_data.get("transaction_date"),
                txn_data.get("description", ""),
                Decimal(str(txn_data.get("debit_amount", 0))),
                Decimal(str(txn_data.get("credit_amount", 0))),
                txn_data.get("bank_reference"),
            )
            
            if existing:
                duplicate_count += 1
                continue
            
            # Create transaction
            debit = Decimal(str(txn_data.get("debit_amount", 0)))
            credit = Decimal(str(txn_data.get("credit_amount", 0)))
            
            txn = BankStatementTransaction(
                bank_account_id=bank_account_id,
                reconciliation_id=reconciliation_id,
                import_id=import_id,
                transaction_date=txn_data["transaction_date"],
                value_date=txn_data.get("value_date"),
                description=txn_data["description"],
                reference=txn_data.get("reference"),
                bank_reference=txn_data.get("bank_reference"),
                debit_amount=debit,
                credit_amount=credit,
                running_balance=txn_data.get("balance"),
                source=source,
                match_status=MatchStatus.UNMATCHED,
            )
            
            # Auto-detect Nigerian charges
            if auto_detect_charges:
                charge_info = self._detect_nigerian_charge(txn_data["description"], debit)
                if charge_info:
                    txn.is_bank_charge = True
                    txn.charge_type = charge_info.get("charge_type")
                    txn.charge_detection_method = ChargeDetectionMethod.AUTO
                    
                    # Set specific charge flags
                    if charge_info.get("is_emtl"):
                        txn.is_emtl = True
                    if charge_info.get("is_stamp_duty"):
                        txn.is_stamp_duty = True
                    if charge_info.get("is_vat"):
                        txn.is_vat = True
                    if charge_info.get("is_wht"):
                        txn.is_wht = True
                    
                    charge_count += 1
            
            self.db.add(txn)
            imported_count += 1
        
        await self.db.commit()
        
        # Update import record if provided
        if import_id:
            await self._update_import_record(
                import_id,
                status="completed",
                transaction_count=imported_count,
                duplicate_count=duplicate_count,
            )
        
        return {
            "imported": imported_count,
            "duplicates_skipped": duplicate_count,
            "charges_detected": charge_count,
            "total_processed": imported_count + duplicate_count,
        }
    
    async def _check_duplicate_transaction(
        self,
        bank_account_id: uuid.UUID,
        transaction_date: date,
        description: str,
        debit: Decimal,
        credit: Decimal,
        bank_reference: Optional[str] = None,
    ) -> Optional[BankStatementTransaction]:
        """Check if a transaction already exists to prevent duplicates."""
        query = select(BankStatementTransaction).where(
            and_(
                BankStatementTransaction.bank_account_id == bank_account_id,
                BankStatementTransaction.transaction_date == transaction_date,
                BankStatementTransaction.debit_amount == debit,
                BankStatementTransaction.credit_amount == credit,
            )
        )
        
        # If bank reference provided, use it for exact match
        if bank_reference:
            query = query.where(
                BankStatementTransaction.bank_reference == bank_reference
            )
        else:
            # Fall back to description matching
            query = query.where(
                BankStatementTransaction.description == description
            )
        
        result = await self.db.execute(query.limit(1))
        return result.scalar_one_or_none()
    
    async def _update_import_record(
        self,
        import_id: uuid.UUID,
        status: str,
        transaction_count: int = 0,
        duplicate_count: int = 0,
        error_message: Optional[str] = None,
    ):
        """Update an import record with results."""
        result = await self.db.execute(
            select(BankStatementImport).where(BankStatementImport.id == import_id)
        )
        import_record = result.scalar_one_or_none()
        if import_record:
            import_record.status = status
            import_record.transaction_count = transaction_count
            import_record.duplicate_count = duplicate_count
            import_record.error_message = error_message
            import_record.completed_at = datetime.utcnow()
            await self.db.commit()
    
    def _detect_nigerian_charge(
        self,
        description: str,
        amount: Decimal,
    ) -> Optional[Dict[str, Any]]:
        """
        Detect Nigerian bank charges from transaction description.
        
        Detects:
        - EMTL (Electronic Money Transfer Levy) - N50 on electronic inflows > N10,000
        - Stamp Duty - N50 on electronic transfers > N10,000
        - SMS Alert Fees
        - VAT charges
        - WHT (Withholding Tax)
        - Account Maintenance/COT fees
        - POS fees
        - Transfer fees (NIP/NIBSS)
        """
        if not description:
            return None
            
        desc_lower = description.lower()
        
        # Check each charge type
        for charge_type, patterns in self.NIGERIAN_CHARGE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, desc_lower):
                    result = {
                        "charge_type": charge_type,
                        "is_emtl": charge_type == "emtl",
                        "is_stamp_duty": charge_type == "stamp_duty",
                        "is_vat": charge_type == "vat",
                        "is_wht": charge_type == "wht",
                    }
                    return result
        
        # Check for common charge amounts (heuristic)
        # EMTL and Stamp Duty are typically N50
        if amount == Decimal("50.00"):
            # Could be EMTL or Stamp Duty - check description keywords
            if any(kw in desc_lower for kw in ["levy", "emtl", "e-levy"]):
                return {"charge_type": "emtl", "is_emtl": True}
            elif any(kw in desc_lower for kw in ["stamp", "duty", "sd "]):
                return {"charge_type": "stamp_duty", "is_stamp_duty": True}
        
        return None
    
    async def get_statement_transactions(
        self,
        reconciliation_id: Optional[uuid.UUID] = None,
        bank_account_id: Optional[uuid.UUID] = None,
        match_status: Optional[MatchStatus] = None,
        is_bank_charge: Optional[bool] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[BankStatementTransaction]:
        """
        Get statement transactions with flexible filtering.
        
        Args:
            reconciliation_id: Filter by specific reconciliation
            bank_account_id: Filter by bank account
            match_status: Filter by match status
            is_bank_charge: Filter bank charges only
            start_date: Transaction date range start
            end_date: Transaction date range end
            limit: Maximum results
            offset: Pagination offset
        """
        query = select(BankStatementTransaction)
        
        conditions = []
        if reconciliation_id:
            conditions.append(BankStatementTransaction.reconciliation_id == reconciliation_id)
        if bank_account_id:
            conditions.append(BankStatementTransaction.bank_account_id == bank_account_id)
        if match_status:
            conditions.append(BankStatementTransaction.match_status == match_status)
        if is_bank_charge is not None:
            conditions.append(BankStatementTransaction.is_bank_charge == is_bank_charge)
        if start_date:
            conditions.append(BankStatementTransaction.transaction_date >= start_date)
        if end_date:
            conditions.append(BankStatementTransaction.transaction_date <= end_date)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(BankStatementTransaction.transaction_date.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ===========================================
    # CHARGE RULES MANAGEMENT
    # ===========================================
    
    async def get_charge_rules(
        self,
        entity_id: uuid.UUID,
        is_active: bool = True,
    ) -> List[BankChargeRule]:
        """Get all charge rules for an entity."""
        query = select(BankChargeRule).where(
            and_(
                BankChargeRule.entity_id == entity_id,
                BankChargeRule.is_active == is_active,
            )
        ).order_by(BankChargeRule.priority.desc(), BankChargeRule.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create_charge_rule(
        self,
        entity_id: uuid.UUID,
        name: str,
        description: Optional[str],
        pattern: str,
        charge_type: str,
        fixed_amount: Optional[Decimal] = None,
        percentage: Optional[Decimal] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        gl_account_code: Optional[str] = None,
        priority: int = 0,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> BankChargeRule:
        """Create a new charge detection rule."""
        rule = BankChargeRule(
            entity_id=entity_id,
            name=name,
            description=description,
            pattern=pattern,
            charge_type=charge_type,
            fixed_amount=fixed_amount,
            percentage=percentage,
            min_amount=min_amount,
            max_amount=max_amount,
            gl_account_code=gl_account_code,
            priority=priority,
            created_by_id=created_by_id,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule
    
    # ===========================================
    # MATCHING RULES MANAGEMENT
    # ===========================================
    
    async def get_matching_rules(
        self,
        entity_id: uuid.UUID,
        is_active: bool = True,
    ) -> List[MatchingRule]:
        """Get all matching rules for an entity."""
        query = select(MatchingRule).where(
            and_(
                MatchingRule.entity_id == entity_id,
                MatchingRule.is_active == is_active,
            )
        ).order_by(MatchingRule.priority.desc(), MatchingRule.name)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create_matching_rule(
        self,
        entity_id: uuid.UUID,
        name: str,
        description: Optional[str],
        bank_pattern: str,
        book_pattern: str,
        match_type: MatchType = MatchType.RULE_BASED,
        date_tolerance_days: int = 3,
        amount_tolerance_percent: Optional[Decimal] = None,
        priority: int = 0,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> MatchingRule:
        """Create a new matching rule."""
        rule = MatchingRule(
            entity_id=entity_id,
            name=name,
            description=description,
            bank_pattern=bank_pattern,
            book_pattern=book_pattern,
            match_type=match_type,
            date_tolerance_days=date_tolerance_days,
            amount_tolerance_percent=amount_tolerance_percent,
            priority=priority,
            created_by_id=created_by_id,
        )
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule
    
    # ===========================================
    # GL TRANSACTION MATCHING
    # ===========================================
    
    async def get_gl_transactions_for_bank(
        self,
        entity_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        start_date: date,
        end_date: date,
        include_matched: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get GL journal entry lines for a bank account.
        
        Returns journal entry lines that affect the GL account linked to
        the specified bank account, suitable for reconciliation matching.
        
        Args:
            entity_id: Business entity ID
            bank_account_id: Bank account ID
            start_date: Period start date
            end_date: Period end date
            include_matched: Whether to include already matched entries
            
        Returns:
            List of GL transaction dicts with entry details
        """
        from app.models.accounting import JournalEntry, JournalEntryLine
        
        # Get GL account ID for bank
        gl_account_id = await self.get_gl_account_id_for_bank(bank_account_id, entity_id)
        if not gl_account_id:
            return []
        
        # Query journal entry lines for the bank GL account
        query = (
            select(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntry.entity_id == entity_id,
                JournalEntryLine.account_id == gl_account_id,
                JournalEntry.entry_date >= start_date,
                JournalEntry.entry_date <= end_date,
                JournalEntry.status == "posted",  # Only posted entries
            )
            .order_by(JournalEntry.entry_date)
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        gl_transactions = []
        for line, entry in rows:
            # Calculate net amount (debit is positive for bank, credit is negative)
            amount = float(line.debit_amount or 0) - float(line.credit_amount or 0)
            
            gl_transactions.append({
                "id": str(line.id),
                "journal_entry_id": str(entry.id),
                "entry_number": entry.entry_number,
                "entry_date": entry.entry_date,
                "reference": entry.reference,
                "description": line.description or entry.description,
                "debit_amount": float(line.debit_amount or 0),
                "credit_amount": float(line.credit_amount or 0),
                "net_amount": amount,
                "source_document_type": entry.source_document_type,
                "source_document_id": entry.source_document_id,
            })
        
        return gl_transactions
    
    async def match_statement_to_gl(
        self,
        reconciliation_id: uuid.UUID,
        entity_id: uuid.UUID,
        statement_transaction_id: uuid.UUID,
        journal_entry_line_id: uuid.UUID,
        match_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Match a bank statement transaction to a GL journal entry line.
        
        This creates a direct link between the statement transaction and
        the GL entry, enabling full audit trail from bank to books.
        
        Args:
            reconciliation_id: Reconciliation ID
            entity_id: Business entity ID
            statement_transaction_id: Bank statement transaction ID
            journal_entry_line_id: GL journal entry line ID
            match_notes: Optional notes for the match
            
        Returns:
            Match result with details
        """
        from app.models.accounting import JournalEntry, JournalEntryLine
        
        # Get statement transaction
        stmt_result = await self.db.execute(
            select(BankStatementTransaction)
            .where(BankStatementTransaction.id == statement_transaction_id)
        )
        stmt_txn = stmt_result.scalar_one_or_none()
        
        if not stmt_txn:
            return {"success": False, "error": "Statement transaction not found"}
        
        # Get GL entry line
        gl_result = await self.db.execute(
            select(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(JournalEntryLine.id == journal_entry_line_id)
        )
        gl_row = gl_result.one_or_none()
        
        if not gl_row:
            return {"success": False, "error": "GL journal entry line not found"}
        
        gl_line, gl_entry = gl_row
        
        # Calculate amounts for comparison
        gl_amount = float(gl_line.debit_amount or 0) - float(gl_line.credit_amount or 0)
        stmt_amount = float(stmt_txn.amount)
        
        # Update statement transaction with GL match
        stmt_txn.match_status = MatchStatus.MANUAL_MATCHED
        stmt_txn.match_type = MatchType.MANUAL
        stmt_txn.match_confidence = Decimal("100.0")
        stmt_txn.matched_at = datetime.utcnow()
        stmt_txn.match_notes = match_notes
        
        # Store GL reference in metadata or a dedicated field
        if not hasattr(stmt_txn, 'matched_gl_entry_id'):
            # Store in metadata if dedicated field not available
            if stmt_txn.metadata is None:
                stmt_txn.metadata = {}
            stmt_txn.metadata["matched_gl_entry_id"] = str(journal_entry_line_id)
            stmt_txn.metadata["matched_journal_entry_id"] = str(gl_entry.id)
            stmt_txn.metadata["matched_entry_number"] = gl_entry.entry_number
        
        await self.db.commit()
        
        return {
            "success": True,
            "statement_transaction_id": str(statement_transaction_id),
            "journal_entry_line_id": str(journal_entry_line_id),
            "journal_entry_id": str(gl_entry.id),
            "entry_number": gl_entry.entry_number,
            "statement_amount": stmt_amount,
            "gl_amount": gl_amount,
            "amount_difference": abs(stmt_amount - gl_amount),
            "match_notes": match_notes,
        }
    
    async def auto_match_to_gl(
        self,
        reconciliation_id: uuid.UUID,
        entity_id: uuid.UUID,
        amount_tolerance: Decimal = Decimal("0.01"),
        date_tolerance_days: int = 3,
    ) -> Dict[str, Any]:
        """
        Automatically match unmatched statement transactions to GL entries.
        
        Uses exact and fuzzy matching based on:
        - Amount (with tolerance)
        - Date (with tolerance in days)
        - Reference matching
        
        Args:
            reconciliation_id: Reconciliation ID
            entity_id: Business entity ID
            amount_tolerance: Maximum amount difference for matching
            date_tolerance_days: Maximum days difference for matching
            
        Returns:
            Match results with statistics
        """
        # Get reconciliation
        recon = await self.get_reconciliation(reconciliation_id, entity_id)
        if not recon:
            return {"success": False, "error": "Reconciliation not found"}
        
        # Get unmatched statement transactions
        unmatched_result = await self.db.execute(
            select(BankStatementTransaction)
            .where(
                BankStatementTransaction.reconciliation_id == reconciliation_id,
                BankStatementTransaction.match_status == MatchStatus.UNMATCHED,
            )
        )
        unmatched_stmt = list(unmatched_result.scalars().all())
        
        if not unmatched_stmt:
            return {
                "success": True,
                "matched_count": 0,
                "unmatched_remaining": 0,
                "message": "No unmatched statement transactions found",
            }
        
        # Get GL transactions for the bank account
        gl_txns = await self.get_gl_transactions_for_bank(
            entity_id=entity_id,
            bank_account_id=recon.bank_account_id,
            start_date=recon.period_start - timedelta(days=date_tolerance_days),
            end_date=recon.period_end + timedelta(days=date_tolerance_days),
        )
        
        if not gl_txns:
            return {
                "success": True,
                "matched_count": 0,
                "unmatched_remaining": len(unmatched_stmt),
                "message": "No GL transactions found for matching",
            }
        
        # Build index of GL transactions by amount for faster matching
        gl_by_amount = {}
        for gl_txn in gl_txns:
            amt_key = round(abs(gl_txn["net_amount"]), 2)
            if amt_key not in gl_by_amount:
                gl_by_amount[amt_key] = []
            gl_by_amount[amt_key].append(gl_txn)
        
        matched_count = 0
        matches = []
        
        for stmt in unmatched_stmt:
            stmt_amount = abs(float(stmt.amount))
            stmt_date = stmt.transaction_date
            
            # Look for potential matches
            best_match = None
            best_score = 0
            
            # Check exact amount first
            amt_key = round(stmt_amount, 2)
            potential_matches = gl_by_amount.get(amt_key, [])
            
            # Also check within tolerance
            for tol in [-float(amount_tolerance), float(amount_tolerance)]:
                tol_key = round(stmt_amount + tol, 2)
                if tol_key in gl_by_amount:
                    potential_matches.extend(gl_by_amount[tol_key])
            
            for gl_txn in potential_matches:
                # Check date tolerance
                gl_date = gl_txn["entry_date"]
                date_diff = abs((stmt_date - gl_date).days)
                
                if date_diff > date_tolerance_days:
                    continue
                
                # Calculate match score
                amount_diff = abs(stmt_amount - abs(gl_txn["net_amount"]))
                score = 100 - (date_diff * 5) - (amount_diff * 10)
                
                # Boost score for reference matches
                if stmt.reference and gl_txn.get("reference"):
                    if stmt.reference.lower() in gl_txn["reference"].lower() or \
                       gl_txn["reference"].lower() in stmt.reference.lower():
                        score += 20
                
                if score > best_score:
                    best_score = score
                    best_match = gl_txn
            
            if best_match and best_score >= 70:
                # Apply match
                match_result = await self.match_statement_to_gl(
                    reconciliation_id=reconciliation_id,
                    entity_id=entity_id,
                    statement_transaction_id=stmt.id,
                    journal_entry_line_id=uuid.UUID(best_match["id"]),
                    match_notes=f"Auto-matched with score {best_score:.0f}",
                )
                
                if match_result.get("success"):
                    matched_count += 1
                    matches.append({
                        "statement_id": str(stmt.id),
                        "gl_entry_id": best_match["id"],
                        "score": best_score,
                    })
                    
                    # Remove from pool to avoid double matching
                    gl_by_amount.get(amt_key, []).remove(best_match) if best_match in gl_by_amount.get(amt_key, []) else None
        
        return {
            "success": True,
            "matched_count": matched_count,
            "unmatched_remaining": len(unmatched_stmt) - matched_count,
            "total_processed": len(unmatched_stmt),
            "matches": matches,
        }
    
    # ===========================================
    # AUTO-MATCHING (Enhanced with MatchingEngine)
    # ===========================================
    
    async def auto_match_transactions(
        self,
        reconciliation_id: uuid.UUID,
        entity_id: uuid.UUID,
        config: Optional[MatchingConfig] = None,
    ) -> Dict[str, Any]:
        """
        Automatically match statement transactions with book transactions.
        
        Uses the MatchingEngine for intelligent matching with:
        - Exact matching
        - Rule-based matching (user-defined rules)
        - Fuzzy matching (date/amount tolerance)
        - One-to-many matching
        - Many-to-one matching
        
        Args:
            reconciliation_id: The reconciliation to match
            entity_id: The entity ID for fetching rules
            config: Optional matching configuration
            
        Returns:
            Dict with match statistics and matched pairs
        """
        # Get unmatched statement transactions
        stmt_txns = await self.get_statement_transactions(
            reconciliation_id=reconciliation_id,
            match_status=MatchStatus.UNMATCHED,
        )
        
        if not stmt_txns:
            return {
                "total_unmatched": 0,
                "auto_matched": 0,
                "remaining_unmatched": 0,
                "matches": [],
            }
        
        # Get book transactions for the period
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        book_txns = await self._get_unmatched_book_transactions(
            entity_id=entity_id,
            bank_account_id=recon.bank_account_id,
            start_date=recon.period_start - timedelta(days=3),  # Buffer for fuzzy matching
            end_date=recon.period_end + timedelta(days=3),
        )
        
        # Get matching rules
        rules = await self.get_matching_rules(entity_id)
        
        # Use default config if not provided
        if config is None:
            config = MatchingConfig(
                date_tolerance_days=3,
                amount_tolerance_percent=Decimal("0.01"),  # 1% tolerance
                min_confidence=70.0,
                enable_fuzzy=True,
                enable_one_to_many=True,
                enable_many_to_one=True,
            )
        
        # Run matching engine
        match_result = await self.matching_engine.auto_match(
            bank_transactions=stmt_txns,
            book_transactions=book_txns,
            rules=rules,
            config=config,
        )
        
        # Apply matches
        applied_matches = []
        for match in match_result.get("matches", []):
            await self._apply_match(match)
            applied_matches.append(match)
        
        # Update reconciliation statistics
        await self._update_reconciliation_statistics(reconciliation_id)
        
        return {
            "total_unmatched": len(stmt_txns),
            "auto_matched": len(applied_matches),
            "remaining_unmatched": len(stmt_txns) - len(applied_matches),
            "matches": applied_matches,
            "match_breakdown": match_result.get("breakdown", {}),
        }
    
    async def _get_unmatched_book_transactions(
        self,
        entity_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        start_date: date,
        end_date: date,
    ) -> List[Transaction]:
        """Get book transactions that haven't been matched yet."""
        # Get already matched transaction IDs
        matched_result = await self.db.execute(
            select(BankStatementTransaction.matched_transaction_id).where(
                and_(
                    BankStatementTransaction.bank_account_id == bank_account_id,
                    BankStatementTransaction.matched_transaction_id.isnot(None),
                )
            )
        )
        matched_ids = {row[0] for row in matched_result.fetchall() if row[0]}
        
        # Get book transactions excluding already matched
        query = select(Transaction).where(
            and_(
                Transaction.entity_id == entity_id,
                Transaction.transaction_date >= start_date,
                Transaction.transaction_date <= end_date,
            )
        )
        
        if matched_ids:
            query = query.where(Transaction.id.notin_(matched_ids))
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def _apply_match(self, match: Dict[str, Any]):
        """Apply a match result to the database."""
        stmt_ids = match.get("statement_transaction_ids", [])
        book_ids = match.get("book_transaction_ids", [])
        match_type = match.get("match_type", MatchType.AUTO)
        confidence = match.get("confidence", 100.0)
        
        # Update statement transactions
        for stmt_id in stmt_ids:
            result = await self.db.execute(
                select(BankStatementTransaction).where(
                    BankStatementTransaction.id == uuid.UUID(stmt_id)
                    if isinstance(stmt_id, str) else
                    BankStatementTransaction.id == stmt_id
                )
            )
            stmt_txn = result.scalar_one_or_none()
            if stmt_txn:
                stmt_txn.match_status = MatchStatus.AUTO_MATCHED
                stmt_txn.match_type = match_type
                stmt_txn.match_confidence = Decimal(str(confidence))
                stmt_txn.matched_at = datetime.utcnow()
                
                # For one-to-one, set the matched transaction ID
                if len(book_ids) == 1:
                    book_id = book_ids[0]
                    stmt_txn.matched_transaction_id = (
                        uuid.UUID(book_id) if isinstance(book_id, str) else book_id
                    )
                else:
                    # For one-to-many/many-to-one, store as JSON
                    stmt_txn.matched_transaction_ids = [
                        str(bid) if not isinstance(bid, str) else bid
                        for bid in book_ids
                    ]
        
        await self.db.commit()
    
    # ===========================================
    # MANUAL MATCHING
    # ===========================================
    
    async def match_transactions(
        self,
        statement_transaction_id: uuid.UUID,
        book_transaction_ids: List[uuid.UUID],
        matched_by_id: uuid.UUID,
        match_type: MatchType = MatchType.MANUAL,
        notes: Optional[str] = None,
    ) -> BankStatementTransaction:
        """
        Manually match a statement transaction with one or more book transactions.
        
        Supports:
        - One-to-one matching (single book transaction)
        - One-to-many matching (multiple book transactions)
        """
        result = await self.db.execute(
            select(BankStatementTransaction).where(
                BankStatementTransaction.id == statement_transaction_id
            )
        )
        stmt_txn = result.scalar_one_or_none()
        if not stmt_txn:
            raise ValueError("Statement transaction not found")
        
        stmt_txn.match_status = MatchStatus.MANUAL_MATCHED
        stmt_txn.match_type = match_type
        stmt_txn.match_confidence = Decimal("100.00")
        stmt_txn.matched_at = datetime.utcnow()
        stmt_txn.matched_by_id = matched_by_id
        stmt_txn.match_notes = notes
        
        if len(book_transaction_ids) == 1:
            stmt_txn.matched_transaction_id = book_transaction_ids[0]
        else:
            # One-to-many: store as JSON array
            stmt_txn.matched_transaction_ids = [str(bid) for bid in book_transaction_ids]
            stmt_txn.match_type = MatchType.ONE_TO_MANY
        
        await self.db.commit()
        await self.db.refresh(stmt_txn)
        
        # Update reconciliation statistics
        if stmt_txn.reconciliation_id:
            await self._update_reconciliation_statistics(stmt_txn.reconciliation_id)
        
        return stmt_txn
    
    async def match_many_to_one(
        self,
        statement_transaction_ids: List[uuid.UUID],
        book_transaction_id: uuid.UUID,
        matched_by_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> List[BankStatementTransaction]:
        """
        Match multiple statement transactions to a single book transaction.
        
        Used for split transactions or multiple bank entries for one book entry.
        """
        matched_txns = []
        
        for stmt_id in statement_transaction_ids:
            result = await self.db.execute(
                select(BankStatementTransaction).where(
                    BankStatementTransaction.id == stmt_id
                )
            )
            stmt_txn = result.scalar_one_or_none()
            if stmt_txn:
                stmt_txn.match_status = MatchStatus.MANUAL_MATCHED
                stmt_txn.match_type = MatchType.MANY_TO_ONE
                stmt_txn.matched_transaction_id = book_transaction_id
                stmt_txn.match_confidence = Decimal("100.00")
                stmt_txn.matched_at = datetime.utcnow()
                stmt_txn.matched_by_id = matched_by_id
                stmt_txn.match_notes = notes
                matched_txns.append(stmt_txn)
        
        await self.db.commit()
        
        # Update reconciliation statistics
        if matched_txns and matched_txns[0].reconciliation_id:
            await self._update_reconciliation_statistics(matched_txns[0].reconciliation_id)
        
        return matched_txns
    
    async def unmatch_transaction(
        self,
        statement_transaction_id: uuid.UUID,
    ) -> BankStatementTransaction:
        """Unmatch a previously matched transaction."""
        result = await self.db.execute(
            select(BankStatementTransaction).where(
                BankStatementTransaction.id == statement_transaction_id
            )
        )
        stmt_txn = result.scalar_one_or_none()
        if not stmt_txn:
            raise ValueError("Statement transaction not found")
        
        reconciliation_id = stmt_txn.reconciliation_id
        
        stmt_txn.match_status = MatchStatus.UNMATCHED
        stmt_txn.match_type = None
        stmt_txn.matched_transaction_id = None
        stmt_txn.matched_transaction_ids = None
        stmt_txn.match_confidence = None
        stmt_txn.matched_at = None
        stmt_txn.matched_by_id = None
        stmt_txn.match_notes = None
        
        await self.db.commit()
        await self.db.refresh(stmt_txn)
        
        # Update reconciliation statistics
        if reconciliation_id:
            await self._update_reconciliation_statistics(reconciliation_id)
        
        return stmt_txn
    
    async def _update_reconciliation_statistics(self, reconciliation_id: uuid.UUID):
        """Update match counts and statistics on a reconciliation."""
        result = await self.db.execute(
            select(BankReconciliation).where(BankReconciliation.id == reconciliation_id)
        )
        recon = result.scalar_one_or_none()
        if not recon:
            return
        
        # Count transactions by status
        stats = await self.db.execute(
            select(
                BankStatementTransaction.match_status,
                func.count(BankStatementTransaction.id).label("count"),
            ).where(
                BankStatementTransaction.reconciliation_id == reconciliation_id
            ).group_by(BankStatementTransaction.match_status)
        )
        
        status_counts = {row[0]: row[1] for row in stats.fetchall()}
        
        total = sum(status_counts.values())
        matched = sum(
            status_counts.get(s, 0) 
            for s in [MatchStatus.AUTO_MATCHED, MatchStatus.MANUAL_MATCHED, MatchStatus.RECONCILED]
        )
        
        recon.total_transactions = total
        recon.matched_transactions = matched
        recon.unmatched_bank_transactions = total - matched
        
        await self.db.commit()
    
    # ===========================================
    # RECONCILIATION MANAGEMENT
    # ===========================================
    
    async def create_reconciliation(
        self,
        entity_id: uuid.UUID,
        bank_account_id: uuid.UUID,
        reconciliation_date: date,
        period_start: date,
        period_end: date,
        statement_ending_balance: Decimal,
        ledger_ending_balance: Decimal,
        reference: Optional[str] = None,
        notes: Optional[str] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> BankReconciliation:
        """
        Create a new bank reconciliation.

        Initializes a reconciliation in DRAFT status with computed difference.
        """
        # Calculate initial difference
        difference = statement_ending_balance - ledger_ending_balance

        recon = BankReconciliation(
            entity_id=entity_id,
            bank_account_id=bank_account_id,
            reconciliation_date=reconciliation_date,
            period_start=period_start,
            period_end=period_end,
            reference=reference,
            statement_ending_balance=statement_ending_balance,
            ledger_ending_balance=ledger_ending_balance,
            adjusted_bank_balance=statement_ending_balance,
            adjusted_book_balance=ledger_ending_balance,
            difference=difference,
            status=ReconciliationStatus.DRAFT,
            notes=notes,
            created_by_id=created_by_id,
        )
        self.db.add(recon)
        await self.db.commit()
        await self.db.refresh(recon)
        return recon
    
    async def get_reconciliation(
        self,
        reconciliation_id: uuid.UUID,
    ) -> Optional[BankReconciliation]:
        """Get a reconciliation by ID."""
        result = await self.db.execute(
            select(BankReconciliation)
            .options(selectinload(BankReconciliation.adjustments))
            .where(BankReconciliation.id == reconciliation_id)
        )
        return result.scalar_one_or_none()
    
    async def get_reconciliations(
        self,
        bank_account_id: Optional[uuid.UUID] = None,
        entity_id: Optional[uuid.UUID] = None,
        status: Optional[ReconciliationStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BankReconciliation]:
        """Get reconciliations with optional filtering."""
        query = select(BankReconciliation)
        
        if bank_account_id:
            query = query.where(BankReconciliation.bank_account_id == bank_account_id)
        
        if entity_id:
            query = query.join(BankAccount).where(BankAccount.entity_id == entity_id)
        
        if status:
            query = query.where(BankReconciliation.status == status)
        
        query = query.order_by(BankReconciliation.reconciliation_date.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ===========================================
    # ADJUSTMENT MANAGEMENT
    # ===========================================
    
    async def add_adjustment(
        self,
        reconciliation_id: uuid.UUID,
        adjustment_type: AdjustmentType,
        amount: Decimal,
        description: str,
        reference: Optional[str] = None,
        affects_bank: bool = True,
        affects_book: bool = False,
        statement_transaction_id: Optional[uuid.UUID] = None,
        gl_account_code: Optional[str] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> ReconciliationAdjustment:
        """
        Add an adjustment to a reconciliation.
        
        Common Nigerian adjustments:
        - Deposits in transit (affects bank +)
        - Outstanding checks (affects bank -)
        - Bank charges (affects book -)
        - Interest earned (affects book +)
        - EMTL charges (affects book -)
        - Stamp duty (affects book -)
        - VAT/WHT (affects book -)
        - Errors (correction)
        """
        # Verify reconciliation exists and is not completed
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.status in [ReconciliationStatus.COMPLETED, ReconciliationStatus.APPROVED]:
            raise ValueError("Cannot add adjustments to completed/approved reconciliation")
        
        adjustment = ReconciliationAdjustment(
            reconciliation_id=reconciliation_id,
            adjustment_type=adjustment_type,
            amount=amount,
            description=description,
            reference=reference,
            affects_bank=affects_bank,
            affects_book=affects_book,
            statement_transaction_id=statement_transaction_id,
            gl_account_code=gl_account_code,
            created_by_id=created_by_id,
        )
        self.db.add(adjustment)
        
        # Recalculate reconciliation balances
        await self._recalculate_reconciliation(recon)
        
        await self.db.commit()
        await self.db.refresh(adjustment)
        return adjustment
    
    async def delete_adjustment(
        self,
        adjustment_id: uuid.UUID,
    ) -> bool:
        """Delete an adjustment and recalculate reconciliation."""
        result = await self.db.execute(
            select(ReconciliationAdjustment).where(
                ReconciliationAdjustment.id == adjustment_id
            )
        )
        adjustment = result.scalar_one_or_none()
        
        if not adjustment:
            return False
        
        reconciliation_id = adjustment.reconciliation_id
        
        # Verify reconciliation is editable
        recon = await self.get_reconciliation(reconciliation_id)
        if recon and recon.status in [ReconciliationStatus.COMPLETED, ReconciliationStatus.APPROVED]:
            raise ValueError("Cannot delete adjustments from completed/approved reconciliation")
        
        await self.db.delete(adjustment)
        
        # Recalculate
        if recon:
            await self._recalculate_reconciliation(recon)
        
        await self.db.commit()
        return True
    
    async def get_adjustments(
        self,
        reconciliation_id: uuid.UUID,
        adjustment_type: Optional[AdjustmentType] = None,
        is_posted: Optional[bool] = None,
    ) -> List[ReconciliationAdjustment]:
        """Get adjustments for a reconciliation."""
        query = select(ReconciliationAdjustment).where(
            ReconciliationAdjustment.reconciliation_id == reconciliation_id
        )
        
        if adjustment_type:
            query = query.where(ReconciliationAdjustment.adjustment_type == adjustment_type)
        
        if is_posted is not None:
            query = query.where(ReconciliationAdjustment.is_posted == is_posted)
        
        query = query.order_by(ReconciliationAdjustment.created_at)
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def post_adjustments(
        self,
        reconciliation_id: uuid.UUID,
        posted_by_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Post all unposted adjustments to the general ledger.
        
        Creates journal entries for each adjustment that affects the book.
        """
        adjustments = await self.get_adjustments(
            reconciliation_id=reconciliation_id,
            is_posted=False,
        )
        
        posted_count = 0
        errors = []
        
        for adj in adjustments:
            try:
                # Only post adjustments that affect the book
                if adj.affects_book:
                    # Here you would integrate with journal entry service
                    # For now, just mark as posted
                    adj.is_posted = True
                    adj.posted_at = datetime.utcnow()
                    adj.posted_by_id = posted_by_id
                    posted_count += 1
            except Exception as e:
                errors.append({
                    "adjustment_id": str(adj.id),
                    "error": str(e),
                })
        
        await self.db.commit()
        
        return {
            "posted": posted_count,
            "errors": errors,
            "total": len(adjustments),
        }
    
    async def auto_create_charge_adjustments(
        self,
        reconciliation_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> List[ReconciliationAdjustment]:
        """
        Automatically create adjustments for detected bank charges.
        
        Finds all bank charge transactions and creates corresponding adjustments.
        """
        # Get unposted charge transactions
        charges = await self.get_statement_transactions(
            reconciliation_id=reconciliation_id,
            is_bank_charge=True,
        )
        
        created_adjustments = []
        
        for charge in charges:
            # Skip if already has an adjustment
            existing = await self.db.execute(
                select(ReconciliationAdjustment).where(
                    and_(
                        ReconciliationAdjustment.reconciliation_id == reconciliation_id,
                        ReconciliationAdjustment.statement_transaction_id == charge.id,
                    )
                )
            )
            if existing.scalar_one_or_none():
                continue
            
            # Determine adjustment type
            if charge.is_emtl:
                adj_type = AdjustmentType.EMTL
            elif charge.is_stamp_duty:
                adj_type = AdjustmentType.STAMP_DUTY
            elif charge.is_vat:
                adj_type = AdjustmentType.VAT
            elif charge.is_wht:
                adj_type = AdjustmentType.WHT
            else:
                adj_type = AdjustmentType.BANK_CHARGES
            
            # Create adjustment
            adjustment = await self.add_adjustment(
                reconciliation_id=reconciliation_id,
                adjustment_type=adj_type,
                amount=charge.debit_amount or Decimal("0"),
                description=f"Auto-detected: {charge.description}",
                reference=charge.bank_reference,
                affects_bank=False,  # Already on bank statement
                affects_book=True,   # Needs to be recorded in books
                statement_transaction_id=charge.id,
                created_by_id=created_by_id,
            )
            created_adjustments.append(adjustment)
        
        return created_adjustments
    
    async def _recalculate_reconciliation(
        self,
        recon: BankReconciliation,
    ):
        """Recalculate adjusted balances based on all adjustments."""
        # Get all adjustments
        adjustments = await self.get_adjustments(recon.id)
        
        bank_adjustments = Decimal("0")
        book_adjustments = Decimal("0")
        
        for adj in adjustments:
            # Determine sign based on adjustment type
            amount = adj.amount
            
            # Bank adjustments
            if adj.affects_bank:
                if adj.adjustment_type in [
                    AdjustmentType.DEPOSIT_IN_TRANSIT,
                    AdjustmentType.INTEREST_EARNED,
                ]:
                    bank_adjustments += amount
                elif adj.adjustment_type in [
                    AdjustmentType.OUTSTANDING_CHECK,
                    AdjustmentType.BANK_CHARGES,
                    AdjustmentType.BANK_ERROR,
                ]:
                    bank_adjustments -= amount
            
            # Book adjustments
            if adj.affects_book:
                if adj.adjustment_type in [
                    AdjustmentType.INTEREST_EARNED,
                    AdjustmentType.OUTSTANDING_DEPOSIT,
                ]:
                    book_adjustments += amount
                elif adj.adjustment_type in [
                    AdjustmentType.BANK_CHARGES,
                    AdjustmentType.EMTL,
                    AdjustmentType.STAMP_DUTY,
                    AdjustmentType.VAT,
                    AdjustmentType.WHT,
                    AdjustmentType.SMS_FEE,
                    AdjustmentType.MAINTENANCE_FEE,
                    AdjustmentType.BOOK_ERROR,
                ]:
                    book_adjustments -= amount
        
        # Calculate adjusted balances
        recon.adjusted_bank_balance = recon.statement_ending_balance + bank_adjustments
        recon.adjusted_book_balance = recon.ledger_ending_balance + book_adjustments
        recon.difference = recon.adjusted_bank_balance - recon.adjusted_book_balance
        
        # Store adjustment totals
        recon.deposits_in_transit = sum(
            adj.amount for adj in adjustments 
            if adj.adjustment_type == AdjustmentType.DEPOSIT_IN_TRANSIT
        )
        recon.outstanding_checks = sum(
            adj.amount for adj in adjustments 
            if adj.adjustment_type == AdjustmentType.OUTSTANDING_CHECK
        )
        recon.bank_charges = sum(
            adj.amount for adj in adjustments 
            if adj.adjustment_type in [
                AdjustmentType.BANK_CHARGES, AdjustmentType.EMTL,
                AdjustmentType.STAMP_DUTY, AdjustmentType.SMS_FEE,
                AdjustmentType.MAINTENANCE_FEE,
            ]
        )
        recon.interest_earned = sum(
            adj.amount for adj in adjustments 
            if adj.adjustment_type == AdjustmentType.INTEREST_EARNED
        )
    
    async def complete_reconciliation(
        self,
        reconciliation_id: uuid.UUID,
        completed_by_id: uuid.UUID,
    ) -> BankReconciliation:
        """Mark reconciliation as completed."""
        result = await self.db.execute(
            select(BankReconciliation).where(BankReconciliation.id == reconciliation_id)
        )
        recon = result.scalar_one_or_none()
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.difference != Decimal("0.00"):
            raise ValueError(
                f"Cannot complete reconciliation with difference of {recon.difference}. "
                "Difference must be zero."
            )
        
        recon.status = ReconciliationStatus.COMPLETED
        recon.completed_at = datetime.utcnow()
        recon.completed_by_id = completed_by_id
        
        # Update bank account
        account_result = await self.db.execute(
            select(BankAccount).where(BankAccount.id == recon.bank_account_id)
        )
        account = account_result.scalar_one_or_none()
        if account:
            account.last_reconciled_date = recon.reconciliation_date
            account.last_reconciled_balance = recon.statement_ending_balance
            account.current_balance = recon.statement_ending_balance

        await self.db.commit()
        await self.db.refresh(recon)
        return recon
    
    # ===========================================
    # WORKFLOW MANAGEMENT
    # ===========================================
    
    async def submit_for_review(
        self,
        reconciliation_id: uuid.UUID,
        submitted_by_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> BankReconciliation:
        """
        Submit a reconciliation for review/approval.
        
        Validates:
        - Difference must be zero
        - Must be in DRAFT or IN_PROGRESS status
        """
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.status not in [ReconciliationStatus.DRAFT, ReconciliationStatus.IN_PROGRESS]:
            raise ValueError(
                f"Cannot submit reconciliation in {recon.status.value} status. "
                "Must be in draft or in_progress."
            )
        
        if recon.difference != Decimal("0.00"):
            raise ValueError(
                f"Cannot submit reconciliation with difference of {recon.difference}. "
                "Difference must be zero."
            )
        
        recon.status = ReconciliationStatus.PENDING_REVIEW
        recon.submitted_at = datetime.utcnow()
        recon.submitted_by_id = submitted_by_id
        if notes:
            recon.notes = notes
        
        await self.db.commit()
        await self.db.refresh(recon)
        return recon
    
    async def approve_reconciliation(
        self,
        reconciliation_id: uuid.UUID,
        approved_by_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> BankReconciliation:
        """
        Approve a reconciliation that's in review.
        
        Requires PENDING_REVIEW or COMPLETED status.
        """
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.status not in [ReconciliationStatus.PENDING_REVIEW, ReconciliationStatus.COMPLETED]:
            raise ValueError(
                f"Cannot approve reconciliation in {recon.status.value} status. "
                "Must be in_review or completed."
            )
        
        recon.status = ReconciliationStatus.APPROVED
        recon.approved_at = datetime.utcnow()
        recon.approved_by_id = approved_by_id
        if notes:
            recon.approval_notes = notes
        
        # Update bank account last reconciled info
        account_result = await self.db.execute(
            select(BankAccount).where(BankAccount.id == recon.bank_account_id)
        )
        account = account_result.scalar_one_or_none()
        if account:
            account.last_reconciled_date = recon.reconciliation_date
            account.last_reconciled_balance = recon.statement_ending_balance

        await self.db.commit()
        await self.db.refresh(recon)
        return recon

    async def reject_reconciliation(
        self,
        reconciliation_id: uuid.UUID,
        rejected_by_id: uuid.UUID,
        reason: str,
    ) -> BankReconciliation:
        """
        Reject a reconciliation back to draft for corrections.
        
        Requires PENDING_REVIEW status.
        """
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.status != ReconciliationStatus.PENDING_REVIEW:
            raise ValueError(
                f"Cannot reject reconciliation in {recon.status.value} status. "
                "Must be in_review."
            )
        
        recon.status = ReconciliationStatus.REJECTED
        recon.rejected_at = datetime.utcnow()
        recon.rejected_by_id = rejected_by_id
        recon.rejection_reason = reason
        
        await self.db.commit()
        await self.db.refresh(recon)
        return recon
    
    async def reopen_reconciliation(
        self,
        reconciliation_id: uuid.UUID,
        reopened_by_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> BankReconciliation:
        """
        Reopen a rejected reconciliation for corrections.
        """
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        if recon.status != ReconciliationStatus.REJECTED:
            raise ValueError(
                f"Cannot reopen reconciliation in {recon.status.value} status. "
                "Must be rejected."
            )
        
        recon.status = ReconciliationStatus.DRAFT
        recon.reopened_at = datetime.utcnow()
        recon.reopened_by_id = reopened_by_id
        if reason:
            recon.notes = f"{recon.notes or ''}\nReopened: {reason}"
        
        # Clear rejection info
        recon.rejected_at = None
        recon.rejected_by_id = None
        recon.rejection_reason = None
        
        await self.db.commit()
        await self.db.refresh(recon)
        return recon
    
    async def get_reconciliations(
        self,
        bank_account_id: uuid.UUID,
        status: Optional[ReconciliationStatus] = None,
    ) -> List[BankReconciliation]:
        """Get reconciliations for a bank account."""
        query = select(BankReconciliation).where(
            BankReconciliation.bank_account_id == bank_account_id
        )
        if status:
            query = query.where(BankReconciliation.status == status)
        query = query.order_by(BankReconciliation.reconciliation_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    # ===========================================
    # UNMATCHED ITEM MANAGEMENT
    # ===========================================
    
    async def create_unmatched_item(
        self,
        reconciliation_id: uuid.UUID,
        item_type: UnmatchedItemType,
        amount: Decimal,
        description: str,
        transaction_date: date,
        reference: Optional[str] = None,
        statement_transaction_id: Optional[uuid.UUID] = None,
        book_transaction_id: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> UnmatchedItem:
        """Create an unmatched item record for tracking."""
        item = UnmatchedItem(
            reconciliation_id=reconciliation_id,
            item_type=item_type,
            amount=amount,
            description=description,
            transaction_date=transaction_date,
            reference=reference,
            statement_transaction_id=statement_transaction_id,
            book_transaction_id=book_transaction_id,
            notes=notes,
            created_by_id=created_by_id,
            status="open",
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item
    
    async def get_unmatched_items(
        self,
        reconciliation_id: uuid.UUID,
        item_type: Optional[UnmatchedItemType] = None,
        status: Optional[str] = None,
    ) -> List[UnmatchedItem]:
        """Get unmatched items for a reconciliation."""
        query = select(UnmatchedItem).where(
            UnmatchedItem.reconciliation_id == reconciliation_id
        )
        
        if item_type:
            query = query.where(UnmatchedItem.item_type == item_type)
        if status:
            query = query.where(UnmatchedItem.status == status)
        
        query = query.order_by(UnmatchedItem.transaction_date.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def resolve_unmatched_item(
        self,
        item_id: uuid.UUID,
        resolution: str,
        resolved_by_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> UnmatchedItem:
        """Mark an unmatched item as resolved."""
        result = await self.db.execute(
            select(UnmatchedItem).where(UnmatchedItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            raise ValueError("Unmatched item not found")
        
        item.status = "resolved"
        item.resolution = resolution
        item.resolved_by_id = resolved_by_id
        item.resolved_at = datetime.utcnow()
        if notes:
            item.notes = f"{item.notes or ''}\nResolution: {notes}"
        
        await self.db.commit()
        await self.db.refresh(item)
        return item
    
    async def auto_create_unmatched_items(
        self,
        reconciliation_id: uuid.UUID,
        created_by_id: Optional[uuid.UUID] = None,
    ) -> List[UnmatchedItem]:
        """
        Automatically create unmatched items from unmatched transactions.
        """
        # Get unmatched statement transactions (not in book)
        unmatched_bank = await self.get_statement_transactions(
            reconciliation_id=reconciliation_id,
            match_status=MatchStatus.UNMATCHED,
        )
        
        created_items = []
        
        for txn in unmatched_bank:
            # Determine item type based on transaction
            if txn.is_bank_charge:
                if txn.is_emtl:
                    item_type = UnmatchedItemType.EMTL_NOT_BOOKED
                elif txn.is_stamp_duty:
                    item_type = UnmatchedItemType.STAMP_DUTY_NOT_BOOKED
                else:
                    item_type = UnmatchedItemType.CHARGE_NOT_BOOKED
            elif txn.credit_amount and txn.credit_amount > 0:
                item_type = UnmatchedItemType.CREDIT_IN_BANK_ONLY
            else:
                item_type = UnmatchedItemType.DEBIT_IN_BANK_ONLY
            
            item = await self.create_unmatched_item(
                reconciliation_id=reconciliation_id,
                item_type=item_type,
                amount=txn.amount,
                description=txn.description,
                transaction_date=txn.transaction_date,
                reference=txn.bank_reference or txn.reference,
                statement_transaction_id=txn.id,
                created_by_id=created_by_id,
            )
            created_items.append(item)
        
        return created_items
    
    # ===========================================
    # SUMMARY & REPORTING
    # ===========================================
    
    async def get_reconciliation_summary(
        self,
        entity_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Get reconciliation summary for all accounts in an entity."""
        accounts = await self.get_bank_accounts(entity_id)
        
        summary = {
            "total_accounts": len(accounts),
            "accounts": [],
            "summary_stats": {
                "total_pending": 0,
                "total_in_review": 0,
                "total_approved": 0,
                "overdue_count": 0,
            },
        }
        
        today = date.today()
        
        for account in accounts:
            last_recon = await self.db.execute(
                select(BankReconciliation)
                .where(BankReconciliation.bank_account_id == account.id)
                .order_by(BankReconciliation.reconciliation_date.desc())
                .limit(1)
            )
            last_recon = last_recon.scalar_one_or_none()
            
            # Calculate days since last reconciliation
            days_since = None
            is_overdue = False
            if account.last_reconciled_date:
                days_since = (today - account.last_reconciled_date).days
                is_overdue = days_since > 30  # Consider overdue if > 30 days
                if is_overdue:
                    summary["summary_stats"]["overdue_count"] += 1
            
            # Get pending/in-review count
            pending_result = await self.db.execute(
                select(func.count(BankReconciliation.id)).where(
                    and_(
                        BankReconciliation.bank_account_id == account.id,
                        BankReconciliation.status.in_([
                            ReconciliationStatus.DRAFT,
                            ReconciliationStatus.IN_PROGRESS,
                        ])
                    )
                )
            )
            pending_count = pending_result.scalar() or 0
            summary["summary_stats"]["total_pending"] += pending_count
            
            summary["accounts"].append({
                "account_id": str(account.id),
                "bank_name": account.bank_name,
                "account_name": account.account_name,
                "account_number": account.account_number,
                "current_balance": float(account.current_balance),
                "currency": account.currency.value if hasattr(account.currency, 'value') else str(account.currency),
                "last_reconciled_date": (
                    account.last_reconciled_date.isoformat() 
                    if account.last_reconciled_date else None
                ),
                "last_reconciled_balance": (
                    float(account.last_reconciled_balance) 
                    if account.last_reconciled_balance else None
                ),
                "days_since_reconciliation": days_since,
                "is_overdue": is_overdue,
                "last_reconciliation_status": (
                    last_recon.status.value if last_recon else None
                ),
                "has_api_integration": bool(
                    account.mono_account_id or 
                    account.okra_account_id or 
                    account.stitch_account_id
                ),
            })
        
        return summary
    
    async def generate_reconciliation_report(
        self,
        reconciliation_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive reconciliation report.
        
        Returns detailed information for audit purposes.
        """
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        # Get bank account
        account = await self.get_bank_account(recon.bank_account_id)
        
        # Get all adjustments
        adjustments = await self.get_adjustments(reconciliation_id)
        
        # Get transaction statistics
        total_stmt_txns = await self.db.execute(
            select(func.count(BankStatementTransaction.id)).where(
                BankStatementTransaction.reconciliation_id == reconciliation_id
            )
        )
        total_count = total_stmt_txns.scalar() or 0
        
        # Matched stats
        matched_stats = await self.db.execute(
            select(
                BankStatementTransaction.match_status,
                BankStatementTransaction.match_type,
                func.count(BankStatementTransaction.id).label("count"),
                func.sum(BankStatementTransaction.debit_amount).label("total_debit"),
                func.sum(BankStatementTransaction.credit_amount).label("total_credit"),
            ).where(
                BankStatementTransaction.reconciliation_id == reconciliation_id
            ).group_by(
                BankStatementTransaction.match_status,
                BankStatementTransaction.match_type,
            )
        )
        
        match_breakdown = {}
        for row in matched_stats.fetchall():
            status = row[0].value if row[0] else "unknown"
            match_type = row[1].value if row[1] else "none"
            key = f"{status}_{match_type}"
            match_breakdown[key] = {
                "count": row[2],
                "total_debit": float(row[3] or 0),
                "total_credit": float(row[4] or 0),
            }
        
        # Get unmatched items
        unmatched_items = await self.get_unmatched_items(reconciliation_id)
        
        # Build report
        report = {
            "reconciliation_id": str(recon.id),
            "reference": recon.reference,
            "reconciliation_date": recon.reconciliation_date.isoformat(),
            "period": {
                "start": recon.period_start.isoformat(),
                "end": recon.period_end.isoformat(),
            },
            "status": recon.status.value,
            "bank_account": {
                "id": str(account.id) if account else None,
                "bank_name": account.bank_name if account else None,
                "account_number": account.account_number if account else None,
                "account_name": account.account_name if account else None,
            },
            "balances": {
                "statement_ending": float(recon.statement_ending_balance),
                "ledger_ending": float(recon.ledger_ending_balance),
                "adjusted_bank": float(recon.adjusted_bank_balance),
                "adjusted_book": float(recon.adjusted_book_balance),
                "difference": float(recon.difference),
            },
            "adjustments_summary": {
                "deposits_in_transit": float(recon.deposits_in_transit or 0),
                "outstanding_checks": float(recon.outstanding_checks or 0),
                "bank_charges": float(recon.bank_charges or 0),
                "interest_earned": float(recon.interest_earned or 0),
                "other_adjustments": float(recon.other_adjustments or 0),
                "total_adjustments": len(adjustments),
                "posted_adjustments": sum(1 for a in adjustments if a.is_posted),
            },
            "transaction_summary": {
                "total_transactions": total_count,
                "match_breakdown": match_breakdown,
            },
            "unmatched_items": {
                "total": len(unmatched_items),
                "by_type": {},
                "open_count": sum(1 for item in unmatched_items if item.status == "open"),
            },
            "workflow": {
                "created_at": recon.created_at.isoformat() if recon.created_at else None,
                "submitted_at": recon.submitted_at.isoformat() if recon.submitted_at else None,
                "completed_at": recon.completed_at.isoformat() if recon.completed_at else None,
                "approved_at": recon.approved_at.isoformat() if recon.approved_at else None,
                "rejected_at": recon.rejected_at.isoformat() if recon.rejected_at else None,
                "rejection_reason": recon.rejection_reason,
            },
            "is_balanced": recon.difference == Decimal("0.00"),
        }
        
        # Group unmatched items by type
        for item in unmatched_items:
            item_type = item.item_type.value if item.item_type else "unknown"
            if item_type not in report["unmatched_items"]["by_type"]:
                report["unmatched_items"]["by_type"][item_type] = {
                    "count": 0,
                    "total_amount": 0,
                }
            report["unmatched_items"]["by_type"][item_type]["count"] += 1
            report["unmatched_items"]["by_type"][item_type]["total_amount"] += float(item.amount)
        
        return report


# ===========================================
    # GL INTEGRATION - JOURNAL ENTRY CREATION
    # ===========================================
    
    async def create_gl_journal_entries(
        self,
        reconciliation_id: uuid.UUID,
        entity_id: uuid.UUID,
        user_id: uuid.UUID,
        auto_post: bool = True,
    ) -> Dict[str, Any]:
        """
        Create journal entries from reconciliation adjustments.
        
        This is the critical integration point between bank reconciliation
        and the general ledger. Each adjustment that affects the books
        generates a corresponding journal entry.
        
        Nigerian-specific entries created:
        - EMTL (₦50) → Dr EMTL Expense (5200) / Cr Bank
        - Stamp Duty (₦50) → Dr Statutory Charges (5210) / Cr Bank  
        - VAT on Charges → Dr Input VAT (1160) / Cr Bank
        - WHT Deducted → Dr WHT Receivable (1170) / Cr Bank or Revenue
        - Bank Charges → Dr Bank Charges (5100) / Cr Bank
        - SMS Fees → Dr Bank Charges (5100) / Cr Bank
        - Interest Earned → Dr Bank / Cr Interest Income (4200)
        
        Returns:
            Dict with created journal IDs and any errors
        """
        from app.models.accounting import JournalEntry, JournalEntryLine, JournalEntryStatus, JournalEntryType
        
        recon = await self.get_reconciliation(reconciliation_id)
        if not recon:
            raise ValueError("Reconciliation not found")
        
        # Get bank account for GL account code
        account = await self.get_bank_account(recon.bank_account_id)
        if not account:
            raise ValueError("Bank account not found")
        
        bank_gl_code = account.gl_account_code or "1120"  # Default bank GL code
        
        # Get unposted adjustments that affect books
        adjustments = await self.get_adjustments(
            reconciliation_id=reconciliation_id,
            is_posted=False,
        )
        
        book_adjustments = [adj for adj in adjustments if adj.affects_book]
        
        if not book_adjustments:
            return {
                "success": True,
                "journal_entries_created": 0,
                "message": "No unposted book adjustments to process",
            }
        
        # GL Account Mapping for Nigerian charges
        GL_MAPPING = {
            AdjustmentType.EMTL: {"debit": "5200", "debit_name": "EMTL Expense"},
            AdjustmentType.STAMP_DUTY: {"debit": "5210", "debit_name": "Stamp Duty Expense"},
            AdjustmentType.VAT_ON_CHARGES: {"debit": "1160", "debit_name": "VAT Receivable (Input VAT)"},
            AdjustmentType.WHT_DEDUCTION: {"debit": "1170", "debit_name": "WHT Receivable"},
            AdjustmentType.BANK_CHARGE: {"debit": "5100", "debit_name": "Bank Charges"},
            AdjustmentType.SMS_FEE: {"debit": "5100", "debit_name": "Bank Charges"},
            AdjustmentType.MAINTENANCE_FEE: {"debit": "5100", "debit_name": "Bank Charges"},
            AdjustmentType.NIP_CHARGE: {"debit": "5100", "debit_name": "Bank Charges"},
            AdjustmentType.USSD_CHARGE: {"debit": "5100", "debit_name": "Bank Charges"},
            AdjustmentType.INTEREST_INCOME: {"credit": "4200", "credit_name": "Interest Income"},
            AdjustmentType.POS_SETTLEMENT: {"debit": "1130", "debit_name": "Accounts Receivable"},
            AdjustmentType.REVERSAL: {"debit": "5900", "debit_name": "Suspense Account"},
            AdjustmentType.OTHER: {"debit": "5900", "debit_name": "Suspense Account"},
        }
        
        created_entries = []
        errors = []
        
        for adj in book_adjustments:
            try:
                gl_mapping = GL_MAPPING.get(adj.adjustment_type, GL_MAPPING[AdjustmentType.OTHER])
                
                # Create journal entry
                je_ref = f"RECON-{recon.reference or str(reconciliation_id)[:8]}-{adj.id}"[:50]
                
                journal_entry = JournalEntry(
                    entity_id=entity_id,
                    entry_date=recon.reconciliation_date,
                    reference=je_ref,
                    description=f"Bank Reconciliation: {adj.description}",
                    entry_type=JournalEntryType.BANK_RECONCILIATION,
                    status=JournalEntryStatus.POSTED if auto_post else JournalEntryStatus.DRAFT,
                    total_debit=adj.amount,
                    total_credit=adj.amount,
                    source_type="bank_reconciliation",
                    source_id=reconciliation_id,
                    created_by_id=user_id,
                    posted_by_id=user_id if auto_post else None,
                    posted_at=datetime.utcnow() if auto_post else None,
                )
                self.db.add(journal_entry)
                await self.db.flush()  # Get the ID
                
                # Create journal lines
                if adj.adjustment_type == AdjustmentType.INTEREST_INCOME:
                    # Interest earned: Dr Bank, Cr Interest Income
                    debit_line = JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        account_code=bank_gl_code,
                        description=f"Interest earned - {adj.description}",
                        debit_amount=adj.amount,
                        credit_amount=Decimal("0.00"),
                        line_number=1,
                    )
                    credit_line = JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        account_code=gl_mapping.get("credit", "4200"),
                        description=f"Interest income - {adj.description}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=adj.amount,
                        line_number=2,
                    )
                else:
                    # Expense/charge: Dr Expense/Asset, Cr Bank
                    debit_line = JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        account_code=gl_mapping.get("debit", "5900"),
                        description=f"{gl_mapping.get('debit_name', 'Adjustment')} - {adj.description}",
                        debit_amount=adj.amount,
                        credit_amount=Decimal("0.00"),
                        line_number=1,
                    )
                    credit_line = JournalEntryLine(
                        journal_entry_id=journal_entry.id,
                        account_code=bank_gl_code,
                        description=f"Bank - {adj.description}",
                        debit_amount=Decimal("0.00"),
                        credit_amount=adj.amount,
                        line_number=2,
                    )
                
                self.db.add(debit_line)
                self.db.add(credit_line)
                
                # Mark adjustment as posted
                adj.is_posted = True
                adj.posted_at = datetime.utcnow()
                adj.posted_by_id = user_id
                adj.journal_entry_id = journal_entry.id
                
                created_entries.append({
                    "adjustment_id": str(adj.id),
                    "journal_entry_id": str(journal_entry.id),
                    "reference": je_ref,
                    "amount": float(adj.amount),
                    "type": adj.adjustment_type.value if adj.adjustment_type else "other",
                })
                
            except Exception as e:
                errors.append({
                    "adjustment_id": str(adj.id),
                    "error": str(e),
                })
        
        await self.db.commit()
        
        return {
            "success": len(errors) == 0,
            "journal_entries_created": len(created_entries),
            "created_entries": created_entries,
            "errors": errors,
            "total_processed": len(book_adjustments),
        }
    
    async def get_outstanding_items_for_carryforward(
        self,
        bank_account_id: uuid.UUID,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """
        Get outstanding items (deposits in transit, outstanding cheques)
        that need to be carried forward to the next reconciliation period.
        
        This is critical for Nigerian businesses where:
        - Weekend/holiday postings cause timing differences
        - Cheques may take days to clear
        - NIP transfers may have delayed postings
        """
        # Get unresolved unmatched items from previous reconciliations
        query = select(UnmatchedItem).join(
            BankReconciliation
        ).where(
            and_(
                BankReconciliation.bank_account_id == bank_account_id,
                UnmatchedItem.status == "open",
                UnmatchedItem.transaction_date <= as_of_date,
            )
        ).order_by(UnmatchedItem.transaction_date)
        
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        
        deposits_in_transit = []
        outstanding_cheques = []
        other_items = []
        
        for item in items:
            item_dict = {
                "id": str(item.id),
                "amount": float(item.amount),
                "description": item.description,
                "transaction_date": item.transaction_date.isoformat(),
                "reference": item.reference,
                "days_outstanding": (as_of_date - item.transaction_date).days,
            }
            
            if item.item_type in [UnmatchedItemType.DEPOSIT_IN_TRANSIT]:
                deposits_in_transit.append(item_dict)
            elif item.item_type in [UnmatchedItemType.OUTSTANDING_CHEQUE]:
                outstanding_cheques.append(item_dict)
            else:
                other_items.append(item_dict)
        
        return {
            "as_of_date": as_of_date.isoformat(),
            "bank_account_id": str(bank_account_id),
            "deposits_in_transit": {
                "count": len(deposits_in_transit),
                "total": sum(d["amount"] for d in deposits_in_transit),
                "items": deposits_in_transit,
            },
            "outstanding_cheques": {
                "count": len(outstanding_cheques),
                "total": sum(c["amount"] for c in outstanding_cheques),
                "items": outstanding_cheques,
            },
            "other_items": {
                "count": len(other_items),
                "total": sum(o["amount"] for o in other_items),
                "items": other_items,
            },
        }
    
    async def validate_reconciliation_for_period_close(
        self,
        entity_id: uuid.UUID,
        period_end_date: date,
    ) -> Dict[str, Any]:
        """
        Validate that all bank accounts are reconciled for period close.
        
        This is required for month-end close workflow:
        1. All bank accounts must have a completed/approved reconciliation
        2. The reconciliation must cover up to the period end date
        3. All adjustments must be posted to GL
        
        Returns validation result with blocking issues if any.
        """
        accounts = await self.get_bank_accounts(entity_id)
        
        issues = []
        validated_accounts = []
        
        for account in accounts:
            account_status = {
                "account_id": str(account.id),
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "is_valid": False,
                "issues": [],
            }
            
            # Find most recent approved reconciliation
            query = select(BankReconciliation).where(
                and_(
                    BankReconciliation.bank_account_id == account.id,
                    BankReconciliation.status.in_([
                        ReconciliationStatus.APPROVED,
                        ReconciliationStatus.COMPLETED,
                    ]),
                )
            ).order_by(BankReconciliation.period_end.desc()).limit(1)
            
            result = await self.db.execute(query)
            latest_recon = result.scalar_one_or_none()
            
            if not latest_recon:
                account_status["issues"].append("No approved reconciliation found")
                issues.append(f"{account.bank_name} ({account.account_number[-4:]}): No reconciliation")
            elif latest_recon.period_end < period_end_date:
                account_status["issues"].append(
                    f"Reconciliation only covers up to {latest_recon.period_end}, "
                    f"need coverage to {period_end_date}"
                )
                issues.append(
                    f"{account.bank_name} ({account.account_number[-4:]}): "
                    f"Reconciled to {latest_recon.period_end} only"
                )
            else:
                # Check for unposted adjustments
                unposted = await self.get_adjustments(
                    reconciliation_id=latest_recon.id,
                    is_posted=False,
                )
                book_unposted = [a for a in unposted if a.affects_book]
                
                if book_unposted:
                    account_status["issues"].append(
                        f"{len(book_unposted)} unposted adjustments"
                    )
                    issues.append(
                        f"{account.bank_name} ({account.account_number[-4:]}): "
                        f"{len(book_unposted)} unposted adjustments"
                    )
                else:
                    account_status["is_valid"] = True
                    account_status["reconciliation_id"] = str(latest_recon.id)
                    account_status["reconciliation_date"] = latest_recon.reconciliation_date.isoformat()
            
            validated_accounts.append(account_status)
        
        return {
            "is_valid": len(issues) == 0,
            "period_end_date": period_end_date.isoformat(),
            "total_accounts": len(accounts),
            "validated_accounts": sum(1 for a in validated_accounts if a["is_valid"]),
            "accounts": validated_accounts,
            "blocking_issues": issues,
            "can_close_period": len(issues) == 0,
        }


# Factory function
def get_bank_reconciliation_service(db: AsyncSession) -> BankReconciliationService:
    """Get bank reconciliation service instance."""
    return BankReconciliationService(db)
