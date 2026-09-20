"""
Tekvwa Pro Audit - Transaction Matching Engine

Intelligent matching engine for bank reconciliation with support for:
- Exact matching (amount, date, reference)
- Fuzzy matching (date tolerance, partial narration)
- One-to-Many matching (one bank txn to multiple ledger entries)
- Many-to-One matching (multiple bank txns to one ledger entry)
- Rule-based matching (user-defined matching rules)
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_reconciliation import (
    BankStatementTransaction,
    MatchConfidenceLevel,
    MatchingRule,
    MatchStatus,
    MatchType,
)
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass
class MatchCandidate:
    """Represents a potential match between bank and ledger transactions."""
    
    bank_transaction_id: UUID
    ledger_transaction_id: UUID
    match_type: MatchType
    confidence_score: Decimal
    confidence_level: MatchConfidenceLevel
    matching_rule_id: Optional[UUID] = None
    match_group_id: Optional[UUID] = None
    
    # Details for display
    bank_date: Optional[date] = None
    bank_amount: Optional[Decimal] = None
    bank_narration: Optional[str] = None
    ledger_date: Optional[date] = None
    ledger_amount: Optional[Decimal] = None
    ledger_description: Optional[str] = None


@dataclass
class MatchGroup:
    """Represents a group of matched transactions (for one-to-many or many-to-one)."""
    
    group_id: UUID = field(default_factory=uuid4)
    match_type: MatchType = MatchType.EXACT
    bank_transactions: List[UUID] = field(default_factory=list)
    ledger_transactions: List[UUID] = field(default_factory=list)
    total_bank_amount: Decimal = Decimal("0.00")
    total_ledger_amount: Decimal = Decimal("0.00")
    confidence_score: Decimal = Decimal("0.00")


@dataclass
class MatchingConfig:
    """Configuration for the matching engine."""
    
    date_tolerance_days: int = 3
    amount_tolerance_percent: Decimal = Decimal("0.00")
    enable_fuzzy_matching: bool = True
    enable_one_to_many: bool = True
    enable_many_to_one: bool = True
    enable_rule_based: bool = True
    min_confidence_threshold: Decimal = Decimal("70.00")
    max_one_to_many_count: int = 10
    max_many_to_one_count: int = 10


class MatchingEngine:
    """
    Intelligent transaction matching engine for bank reconciliation.
    
    Supports multiple matching strategies:
    1. Exact Match: Same amount, date, and reference
    2. Fuzzy Match: Within tolerance for date and amount
    3. One-to-Many: One bank transaction matches multiple ledger entries
    4. Many-to-One: Multiple bank transactions match one ledger entry
    5. Rule-based: User-defined matching rules
    """
    
    def __init__(self, db: AsyncSession, config: Optional[MatchingConfig] = None):
        self.db = db
        self.config = config or MatchingConfig()
        
        # Cache for loaded data
        self._bank_transactions: Dict[UUID, BankStatementTransaction] = {}
        self._ledger_transactions: Dict[UUID, Transaction] = {}
        self._matching_rules: List[MatchingRule] = []
    
    async def auto_match(
        self,
        bank_account_id: UUID,
        entity_id: UUID,
        period_start: date,
        period_end: date,
    ) -> List[MatchCandidate]:
        """
        Perform automatic matching for all unmatched transactions.
        
        Args:
            bank_account_id: Bank account ID
            entity_id: Entity ID
            period_start: Start of reconciliation period
            period_end: End of reconciliation period
            
        Returns:
            List of match candidates
        """
        # Load unmatched transactions
        await self._load_unmatched_transactions(
            bank_account_id, entity_id, period_start, period_end
        )
        
        # Load matching rules
        await self._load_matching_rules(entity_id, bank_account_id)
        
        all_matches: List[MatchCandidate] = []
        matched_bank_ids: Set[UUID] = set()
        matched_ledger_ids: Set[UUID] = set()
        
        # 1. Exact Matching (highest priority)
        exact_matches = await self._exact_match(matched_bank_ids, matched_ledger_ids)
        all_matches.extend(exact_matches)
        
        # Update matched sets
        for match in exact_matches:
            matched_bank_ids.add(match.bank_transaction_id)
            matched_ledger_ids.add(match.ledger_transaction_id)
        
        # 2. Rule-based Matching
        if self.config.enable_rule_based:
            rule_matches = await self._rule_based_match(
                matched_bank_ids, matched_ledger_ids
            )
            all_matches.extend(rule_matches)
            
            for match in rule_matches:
                matched_bank_ids.add(match.bank_transaction_id)
                matched_ledger_ids.add(match.ledger_transaction_id)
        
        # 3. Fuzzy Matching
        if self.config.enable_fuzzy_matching:
            fuzzy_matches = await self._fuzzy_match(
                matched_bank_ids, matched_ledger_ids
            )
            all_matches.extend(fuzzy_matches)
            
            for match in fuzzy_matches:
                matched_bank_ids.add(match.bank_transaction_id)
                matched_ledger_ids.add(match.ledger_transaction_id)
        
        # 4. One-to-Many Matching
        if self.config.enable_one_to_many:
            otm_matches = await self._one_to_many_match(
                matched_bank_ids, matched_ledger_ids
            )
            all_matches.extend(otm_matches)
            
            for match in otm_matches:
                matched_bank_ids.add(match.bank_transaction_id)
                matched_ledger_ids.add(match.ledger_transaction_id)
        
        # 5. Many-to-One Matching
        if self.config.enable_many_to_one:
            mto_matches = await self._many_to_one_match(
                matched_bank_ids, matched_ledger_ids
            )
            all_matches.extend(mto_matches)
        
        # Filter by confidence threshold
        filtered_matches = [
            m for m in all_matches
            if m.confidence_score >= self.config.min_confidence_threshold
        ]
        
        return filtered_matches
    
    async def _load_unmatched_transactions(
        self,
        bank_account_id: UUID,
        entity_id: UUID,
        period_start: date,
        period_end: date,
    ):
        """Load unmatched bank and ledger transactions into cache."""
        
        # Load unmatched bank transactions
        result = await self.db.execute(
            select(BankStatementTransaction).where(
                and_(
                    BankStatementTransaction.bank_account_id == bank_account_id,
                    BankStatementTransaction.match_status == MatchStatus.UNMATCHED,
                    BankStatementTransaction.transaction_date >= period_start,
                    BankStatementTransaction.transaction_date <= period_end,
                )
            )
        )
        bank_txns = result.scalars().all()
        self._bank_transactions = {t.id: t for t in bank_txns}
        
        # Load unmatched ledger transactions (cash book entries)
        # Assuming gl_account_code links to the bank account
        result = await self.db.execute(
            select(Transaction).where(
                and_(
                    Transaction.entity_id == entity_id,
                    Transaction.date >= period_start,
                    Transaction.date <= period_end,
                    # Filter for bank-related transactions
                    or_(
                        Transaction.category == "Bank Receipt",
                        Transaction.category == "Bank Payment",
                        Transaction.type.in_(["income", "expense"]),
                    ),
                )
            )
        )
        ledger_txns = result.scalars().all()
        self._ledger_transactions = {t.id: t for t in ledger_txns}
        
        logger.info(
            f"Loaded {len(self._bank_transactions)} bank transactions and "
            f"{len(self._ledger_transactions)} ledger transactions for matching"
        )
    
    async def _load_matching_rules(
        self, entity_id: UUID, bank_account_id: Optional[UUID] = None
    ):
        """Load active matching rules."""
        
        query = select(MatchingRule).where(
            and_(
                MatchingRule.entity_id == entity_id,
                MatchingRule.is_active == True,
            )
        )
        
        if bank_account_id:
            query = query.where(
                or_(
                    MatchingRule.bank_account_id == bank_account_id,
                    MatchingRule.bank_account_id.is_(None),
                )
            )
        
        query = query.order_by(MatchingRule.priority)
        
        result = await self.db.execute(query)
        self._matching_rules = list(result.scalars().all())
    
    async def _exact_match(
        self,
        excluded_bank: Set[UUID],
        excluded_ledger: Set[UUID],
    ) -> List[MatchCandidate]:
        """
        Find exact matches (same amount and date).
        """
        matches = []
        
        for bank_id, bank_txn in self._bank_transactions.items():
            if bank_id in excluded_bank:
                continue
            
            bank_amount = self._get_bank_amount(bank_txn)
            
            for ledger_id, ledger_txn in self._ledger_transactions.items():
                if ledger_id in excluded_ledger:
                    continue
                
                ledger_amount = self._get_ledger_amount(ledger_txn)
                
                # Check exact match criteria
                if (
                    bank_amount == ledger_amount
                    and bank_txn.transaction_date == ledger_txn.date
                ):
                    # Calculate confidence score
                    confidence = Decimal("100.00")
                    
                    # Bonus for matching reference
                    if self._references_match(bank_txn, ledger_txn):
                        confidence = Decimal("100.00")
                    
                    matches.append(MatchCandidate(
                        bank_transaction_id=bank_id,
                        ledger_transaction_id=ledger_id,
                        match_type=MatchType.EXACT,
                        confidence_score=confidence,
                        confidence_level=MatchConfidenceLevel.HIGH,
                        bank_date=bank_txn.transaction_date,
                        bank_amount=bank_amount,
                        bank_narration=bank_txn.narration,
                        ledger_date=ledger_txn.date,
                        ledger_amount=ledger_amount,
                        ledger_description=ledger_txn.description,
                    ))
                    break  # Move to next bank transaction
        
        return matches
    
    async def _fuzzy_match(
        self,
        excluded_bank: Set[UUID],
        excluded_ledger: Set[UUID],
    ) -> List[MatchCandidate]:
        """
        Find fuzzy matches (within tolerance for date and amount).
        """
        matches = []
        date_tolerance = timedelta(days=self.config.date_tolerance_days)
        
        for bank_id, bank_txn in self._bank_transactions.items():
            if bank_id in excluded_bank:
                continue
            
            bank_amount = self._get_bank_amount(bank_txn)
            best_match: Optional[MatchCandidate] = None
            best_score = Decimal("0.00")
            
            for ledger_id, ledger_txn in self._ledger_transactions.items():
                if ledger_id in excluded_ledger:
                    continue
                
                ledger_amount = self._get_ledger_amount(ledger_txn)
                
                # Check date within tolerance
                date_diff = abs((bank_txn.transaction_date - ledger_txn.date).days)
                if date_diff > self.config.date_tolerance_days:
                    continue
                
                # Check amount within tolerance
                amount_tolerance = bank_amount * (self.config.amount_tolerance_percent / 100)
                if abs(bank_amount - ledger_amount) > amount_tolerance:
                    continue
                
                # Calculate confidence score
                confidence = self._calculate_fuzzy_confidence(
                    bank_txn, ledger_txn, bank_amount, ledger_amount, date_diff
                )
                
                if confidence > best_score:
                    best_score = confidence
                    best_match = MatchCandidate(
                        bank_transaction_id=bank_id,
                        ledger_transaction_id=ledger_id,
                        match_type=MatchType.FUZZY_DATE if date_diff > 0 else MatchType.FUZZY_AMOUNT,
                        confidence_score=confidence,
                        confidence_level=self._get_confidence_level(confidence),
                        bank_date=bank_txn.transaction_date,
                        bank_amount=bank_amount,
                        bank_narration=bank_txn.narration,
                        ledger_date=ledger_txn.date,
                        ledger_amount=ledger_amount,
                        ledger_description=ledger_txn.description,
                    )
            
            if best_match and best_match.confidence_score >= self.config.min_confidence_threshold:
                matches.append(best_match)
        
        return matches
    
    async def _rule_based_match(
        self,
        excluded_bank: Set[UUID],
        excluded_ledger: Set[UUID],
    ) -> List[MatchCandidate]:
        """
        Find matches using user-defined matching rules.
        """
        matches = []
        
        for rule in self._matching_rules:
            for bank_id, bank_txn in self._bank_transactions.items():
                if bank_id in excluded_bank:
                    continue
                
                # Check if bank transaction matches rule criteria
                if not self._bank_matches_rule(bank_txn, rule):
                    continue
                
                bank_amount = self._get_bank_amount(bank_txn)
                
                for ledger_id, ledger_txn in self._ledger_transactions.items():
                    if ledger_id in excluded_ledger:
                        continue
                    
                    # Check if ledger transaction matches rule criteria
                    if not self._ledger_matches_rule(ledger_txn, rule):
                        continue
                    
                    ledger_amount = self._get_ledger_amount(ledger_txn)
                    
                    # Check date tolerance
                    date_diff = abs((bank_txn.transaction_date - ledger_txn.date).days)
                    if date_diff > rule.date_tolerance_days:
                        continue
                    
                    # Check amount tolerance
                    amount_tolerance = bank_amount * (rule.amount_tolerance_percent / 100)
                    if abs(bank_amount - ledger_amount) > amount_tolerance:
                        continue
                    
                    # Calculate confidence
                    confidence = Decimal("85.00")  # Base confidence for rule match
                    if date_diff == 0:
                        confidence += Decimal("10.00")
                    if bank_amount == ledger_amount:
                        confidence += Decimal("5.00")
                    
                    matches.append(MatchCandidate(
                        bank_transaction_id=bank_id,
                        ledger_transaction_id=ledger_id,
                        match_type=MatchType.RULE_BASED,
                        confidence_score=min(confidence, Decimal("100.00")),
                        confidence_level=self._get_confidence_level(confidence),
                        matching_rule_id=rule.id,
                        bank_date=bank_txn.transaction_date,
                        bank_amount=bank_amount,
                        bank_narration=bank_txn.narration,
                        ledger_date=ledger_txn.date,
                        ledger_amount=ledger_amount,
                        ledger_description=ledger_txn.description,
                    ))
                    
                    # Update rule statistics
                    rule.times_used += 1
                    rule.successful_matches += 1
                    
                    excluded_bank.add(bank_id)
                    excluded_ledger.add(ledger_id)
                    break
        
        return matches
    
    async def _one_to_many_match(
        self,
        excluded_bank: Set[UUID],
        excluded_ledger: Set[UUID],
    ) -> List[MatchCandidate]:
        """
        Find one-to-many matches (one bank transaction = sum of multiple ledger entries).
        """
        matches = []
        
        for bank_id, bank_txn in self._bank_transactions.items():
            if bank_id in excluded_bank:
                continue
            
            bank_amount = self._get_bank_amount(bank_txn)
            
            # Find ledger transactions within date tolerance
            candidates = []
            for ledger_id, ledger_txn in self._ledger_transactions.items():
                if ledger_id in excluded_ledger:
                    continue
                
                date_diff = abs((bank_txn.transaction_date - ledger_txn.date).days)
                if date_diff <= self.config.date_tolerance_days:
                    candidates.append((ledger_id, ledger_txn))
            
            if len(candidates) < 2:
                continue
            
            # Try to find combination that sums to bank amount
            combination = self._find_sum_combination(
                bank_amount,
                [(lid, self._get_ledger_amount(ltxn)) for lid, ltxn in candidates],
                self.config.max_one_to_many_count,
            )
            
            if combination:
                group_id = uuid4()
                
                for ledger_id in combination:
                    ledger_txn = self._ledger_transactions[ledger_id]
                    
                    matches.append(MatchCandidate(
                        bank_transaction_id=bank_id,
                        ledger_transaction_id=ledger_id,
                        match_type=MatchType.ONE_TO_MANY,
                        confidence_score=Decimal("75.00"),
                        confidence_level=MatchConfidenceLevel.MEDIUM,
                        match_group_id=group_id,
                        bank_date=bank_txn.transaction_date,
                        bank_amount=bank_amount,
                        bank_narration=bank_txn.narration,
                        ledger_date=ledger_txn.date,
                        ledger_amount=self._get_ledger_amount(ledger_txn),
                        ledger_description=ledger_txn.description,
                    ))
                    
                    excluded_ledger.add(ledger_id)
                
                excluded_bank.add(bank_id)
        
        return matches
    
    async def _many_to_one_match(
        self,
        excluded_bank: Set[UUID],
        excluded_ledger: Set[UUID],
    ) -> List[MatchCandidate]:
        """
        Find many-to-one matches (sum of multiple bank transactions = one ledger entry).
        """
        matches = []
        
        for ledger_id, ledger_txn in self._ledger_transactions.items():
            if ledger_id in excluded_ledger:
                continue
            
            ledger_amount = self._get_ledger_amount(ledger_txn)
            
            # Find bank transactions within date tolerance
            candidates = []
            for bank_id, bank_txn in self._bank_transactions.items():
                if bank_id in excluded_bank:
                    continue
                
                date_diff = abs((bank_txn.transaction_date - ledger_txn.date).days)
                if date_diff <= self.config.date_tolerance_days:
                    candidates.append((bank_id, bank_txn))
            
            if len(candidates) < 2:
                continue
            
            # Try to find combination that sums to ledger amount
            combination = self._find_sum_combination(
                ledger_amount,
                [(bid, self._get_bank_amount(btxn)) for bid, btxn in candidates],
                self.config.max_many_to_one_count,
            )
            
            if combination:
                group_id = uuid4()
                
                for bank_id in combination:
                    bank_txn = self._bank_transactions[bank_id]
                    
                    matches.append(MatchCandidate(
                        bank_transaction_id=bank_id,
                        ledger_transaction_id=ledger_id,
                        match_type=MatchType.MANY_TO_ONE,
                        confidence_score=Decimal("75.00"),
                        confidence_level=MatchConfidenceLevel.MEDIUM,
                        match_group_id=group_id,
                        bank_date=bank_txn.transaction_date,
                        bank_amount=self._get_bank_amount(bank_txn),
                        bank_narration=bank_txn.narration,
                        ledger_date=ledger_txn.date,
                        ledger_amount=ledger_amount,
                        ledger_description=ledger_txn.description,
                    ))
                    
                    excluded_bank.add(bank_id)
                
                excluded_ledger.add(ledger_id)
        
        return matches
    
    def _find_sum_combination(
        self,
        target: Decimal,
        items: List[Tuple[UUID, Decimal]],
        max_items: int,
    ) -> Optional[List[UUID]]:
        """
        Find a combination of items that sum to target amount.
        Uses dynamic programming approach.
        """
        if len(items) > max_items * 2:
            # Too many items, skip to avoid performance issues
            return None
        
        # Simple subset sum for small sets
        n = len(items)
        if n == 0:
            return None
        
        # Try all combinations up to max_items
        from itertools import combinations
        
        for size in range(2, min(n + 1, max_items + 1)):
            for combo in combinations(items, size):
                total = sum(amount for _, amount in combo)
                if total == target:
                    return [item_id for item_id, _ in combo]
        
        return None
    
    def _get_bank_amount(self, txn: BankStatementTransaction) -> Decimal:
        """Get the effective amount from a bank transaction (positive)."""
        return txn.debit_amount or txn.credit_amount or Decimal("0.00")
    
    def _get_ledger_amount(self, txn: Transaction) -> Decimal:
        """Get the effective amount from a ledger transaction (positive)."""
        return abs(txn.amount) if txn.amount else Decimal("0.00")
    
    def _references_match(
        self, bank_txn: BankStatementTransaction, ledger_txn: Transaction
    ) -> bool:
        """Check if references match between bank and ledger transactions."""
        if not bank_txn.reference or not ledger_txn.reference:
            return False
        
        bank_ref = bank_txn.reference.strip().upper()
        ledger_ref = ledger_txn.reference.strip().upper()
        
        return bank_ref == ledger_ref or bank_ref in ledger_ref or ledger_ref in bank_ref
    
    def _bank_matches_rule(
        self, txn: BankStatementTransaction, rule: MatchingRule
    ) -> bool:
        """Check if bank transaction matches rule criteria."""
        
        # Check narration pattern
        if rule.bank_narration_pattern:
            if not re.search(rule.bank_narration_pattern, txn.narration or "", re.IGNORECASE):
                return False
        
        # Check narration keywords
        if rule.bank_narration_keywords:
            narration_upper = (txn.narration or "").upper()
            if not any(kw.upper() in narration_upper for kw in rule.bank_narration_keywords):
                return False
        
        # Check reference pattern
        if rule.bank_reference_pattern and txn.reference:
            if not re.search(rule.bank_reference_pattern, txn.reference, re.IGNORECASE):
                return False
        
        # Check amount range
        amount = self._get_bank_amount(txn)
        if rule.bank_amount_min and amount < rule.bank_amount_min:
            return False
        if rule.bank_amount_max and amount > rule.bank_amount_max:
            return False
        
        # Check debit/credit
        if rule.bank_is_debit is not None:
            is_debit = txn.debit_amount is not None and txn.debit_amount > 0
            if rule.bank_is_debit != is_debit:
                return False
        
        return True
    
    def _ledger_matches_rule(self, txn: Transaction, rule: MatchingRule) -> bool:
        """Check if ledger transaction matches rule criteria."""
        
        # Check description pattern
        if rule.ledger_description_pattern:
            if not re.search(rule.ledger_description_pattern, txn.description or "", re.IGNORECASE):
                return False
        
        # Check account code
        if rule.ledger_account_code:
            # Would need to check against the GL account in the transaction
            pass
        
        # Check vendor
        if rule.ledger_vendor_id and txn.vendor_id != rule.ledger_vendor_id:
            return False
        
        # Check customer
        if rule.ledger_customer_id and txn.customer_id != rule.ledger_customer_id:
            return False
        
        return True
    
    def _calculate_fuzzy_confidence(
        self,
        bank_txn: BankStatementTransaction,
        ledger_txn: Transaction,
        bank_amount: Decimal,
        ledger_amount: Decimal,
        date_diff: int,
    ) -> Decimal:
        """Calculate confidence score for fuzzy match."""
        
        score = Decimal("70.00")  # Base score
        
        # Amount match bonus
        if bank_amount == ledger_amount:
            score += Decimal("15.00")
        else:
            diff_percent = abs(bank_amount - ledger_amount) / bank_amount * 100
            score += Decimal("15.00") * (1 - diff_percent / 10)
        
        # Date match bonus
        if date_diff == 0:
            score += Decimal("10.00")
        else:
            score += Decimal("10.00") * (1 - Decimal(date_diff) / self.config.date_tolerance_days)
        
        # Reference match bonus
        if self._references_match(bank_txn, ledger_txn):
            score += Decimal("5.00")
        
        return min(score, Decimal("100.00"))
    
    def _get_confidence_level(self, score: Decimal) -> MatchConfidenceLevel:
        """Convert confidence score to confidence level."""
        if score >= Decimal("90.00"):
            return MatchConfidenceLevel.HIGH
        elif score >= Decimal("75.00"):
            return MatchConfidenceLevel.MEDIUM
        else:
            return MatchConfidenceLevel.LOW
    
    async def apply_matches(self, matches: List[MatchCandidate], user_id: UUID):
        """
        Apply match candidates to the database.
        
        Args:
            matches: List of match candidates to apply
            user_id: ID of user applying the matches
        """
        from datetime import datetime
        
        for match in matches:
            # Update bank transaction
            bank_txn = self._bank_transactions.get(match.bank_transaction_id)
            if bank_txn:
                bank_txn.match_status = MatchStatus.AUTO_MATCHED
                bank_txn.matched_transaction_id = match.ledger_transaction_id
                bank_txn.match_type = match.match_type
                bank_txn.match_group_id = match.match_group_id
                bank_txn.match_confidence = match.confidence_score
                bank_txn.match_confidence_level = match.confidence_level
                bank_txn.matched_at = datetime.utcnow()
                bank_txn.matched_by_id = user_id
                bank_txn.matching_rule_id = match.matching_rule_id
        
        await self.db.commit()
    
    async def unmatch(self, bank_transaction_ids: List[UUID]):
        """
        Remove matches for specified bank transactions.
        
        Args:
            bank_transaction_ids: List of bank transaction IDs to unmatch
        """
        result = await self.db.execute(
            select(BankStatementTransaction).where(
                BankStatementTransaction.id.in_(bank_transaction_ids)
            )
        )
        transactions = result.scalars().all()
        
        for txn in transactions:
            txn.match_status = MatchStatus.UNMATCHED
            txn.matched_transaction_id = None
            txn.match_type = None
            txn.match_group_id = None
            txn.match_confidence = None
            txn.match_confidence_level = None
            txn.matched_at = None
            txn.matched_by_id = None
            txn.matching_rule_id = None
        
        await self.db.commit()


async def get_matching_engine(
    db: AsyncSession,
    config: Optional[MatchingConfig] = None,
) -> MatchingEngine:
    """Dependency injection for MatchingEngine."""
    return MatchingEngine(db, config)
