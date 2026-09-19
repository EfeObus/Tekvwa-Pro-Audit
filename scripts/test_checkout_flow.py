#!/usr/bin/env python3
"""
Comprehensive Checkout Flow Test Script

Tests the entire Paystack checkout implementation:
1. Database schema validation
2. API endpoint functionality
3. BillingService integration
4. PaymentTransaction creation
5. Error handling
"""
import asyncio
import sys
import os
from datetime import datetime
from uuid import UUID

# Add project root to path
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/tekvwa_pro_audit')

from sqlalchemy import text, select
from app.database import async_session_maker
from app.models.sku import SKUTier, PaymentTransaction, IntelligenceAddon
from app.services.billing_service import BillingService, BillingCycle, PaymentStatus


class CheckoutTester:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def log_pass(self, test_name: str):
        print(f"  ✅ {test_name}")
        self.passed += 1
    
    def log_fail(self, test_name: str, error: str):
        print(f"  ❌ {test_name}: {error}")
        self.failed += 1
        self.errors.append(f"{test_name}: {error}")
    
    async def test_database_schema(self, session):
        """Test 1: Verify database schema matches expectations."""
        print("\n🔍 Test 1: Database Schema Validation")
        
        # Check required columns exist
        result = await session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'payment_transactions'
        """))
        columns = {row[0] for row in result.fetchall()}
        
        required_columns = [
            'id', 'created_at', 'organization_id', 'reference', 
            'transaction_type', 'status', 'amount_kobo', 'currency',
            'tier', 'billing_cycle', 'authorization_url', 'paystack_access_code',
            'paystack_reference', 'custom_metadata', 'intelligence_addon',
            'additional_users', 'payment_method', 'card_last4', 'card_type',
            'gateway_response', 'paystack_response', 'bank_name', 'failure_reason'
        ]
        
        for col in required_columns:
            if col in columns:
                self.log_pass(f"Column '{col}' exists")
            else:
                self.log_fail(f"Column '{col}'", "Missing from database")
        
        print(f"  📊 Total columns in payment_transactions: {len(columns)}")
    
    async def test_pricing_calculation(self, session):
        """Test 2: Verify pricing calculation."""
        print("\n🔍 Test 2: Pricing Calculation")
        
        service = BillingService(session)
        
        # Test Core tier
        core_monthly = service.calculate_subscription_price(
            tier=SKUTier.CORE,
            billing_cycle=BillingCycle.MONTHLY,
        )
        if core_monthly == 25000:
            self.log_pass(f"Core monthly price: ₦{core_monthly:,}")
        else:
            self.log_fail("Core monthly price", f"Expected 25000, got {core_monthly}")
        
        # Test Professional tier
        pro_monthly = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
        )
        if pro_monthly == 150000:
            self.log_pass(f"Professional monthly price: ₦{pro_monthly:,}")
        else:
            self.log_fail("Professional monthly price", f"Expected 150000, got {pro_monthly}")
        
        # Test Enterprise tier
        ent_monthly = service.calculate_subscription_price(
            tier=SKUTier.ENTERPRISE,
            billing_cycle=BillingCycle.MONTHLY,
        )
        if ent_monthly == 1000000:
            self.log_pass(f"Enterprise monthly price: ₦{ent_monthly:,}")
        else:
            self.log_fail("Enterprise monthly price", f"Expected 1000000, got {ent_monthly}")
        
        # Test annual discount (should be ~15% off)
        core_annual = service.calculate_subscription_price(
            tier=SKUTier.CORE,
            billing_cycle=BillingCycle.ANNUAL,
        )
        expected_annual = 25000 * 12 * 0.85  # 15% discount
        if abs(core_annual - expected_annual) < 1000:  # Allow small variance
            self.log_pass(f"Core annual price: ₦{core_annual:,} (includes discount)")
        else:
            self.log_fail("Core annual price", f"Expected ~{expected_annual:,.0f}, got {core_annual}")
        
        # Test with intelligence addon
        pro_with_intel = service.calculate_subscription_price(
            tier=SKUTier.PROFESSIONAL,
            billing_cycle=BillingCycle.MONTHLY,
            intelligence_addon=IntelligenceAddon.STANDARD,
        )
        if pro_with_intel > pro_monthly:
            self.log_pass(f"Pro + Intelligence addon: ₦{pro_with_intel:,}")
        else:
            self.log_fail("Intelligence addon pricing", "Should be more than base price")
    
    async def test_payment_provider(self, session):
        """Test 3: Verify PaymentProvider (stub mode)."""
        print("\n🔍 Test 3: Payment Provider (Stub Mode)")
        
        service = BillingService(session)
        
        # Check provider is in stub mode
        if service.payment_provider._is_stub:
            self.log_pass("PaymentProvider is in STUB mode (no API key)")
        else:
            self.log_fail("PaymentProvider mode", "Expected stub mode for testing")
        
        # Test initialize_payment in stub mode
        result = await service.payment_provider.initialize_payment(
            email="test@example.com",
            amount_naira=50000,
            reference="TEST-REFERENCE-123",
            callback_url="/payment/callback",
        )
        
        if result.get("status"):
            self.log_pass("Payment initialization succeeded")
            if "stub" in result.get("data", {}).get("authorization_url", "").lower():
                self.log_pass("Stub authorization URL generated")
            else:
                self.log_fail("Authorization URL", "Should contain 'stub'")
        else:
            self.log_fail("Payment initialization", result.get("message", "Failed"))
        
        # Test verify_payment in stub mode
        verify_result = await service.payment_provider.verify_payment("TEST-REFERENCE-123")
        
        if verify_result.success:
            self.log_pass("Payment verification succeeded (stub)")
            if verify_result.status == PaymentStatus.SUCCESS:
                self.log_pass("Payment status is SUCCESS")
        else:
            self.log_fail("Payment verification", "Should succeed in stub mode")
    
    async def test_payment_intent_creation(self, session):
        """Test 4: Test creating a payment intent (full flow)."""
        print("\n🔍 Test 4: Payment Intent Creation")
        
        # Get a real organization ID from the database
        org_result = await session.execute(text("SELECT id FROM organizations LIMIT 1"))
        org_row = org_result.fetchone()
        
        if not org_row:
            self.log_fail("Organization lookup", "No organizations in database")
            return
        
        org_id = org_row[0]
        self.log_pass(f"Found organization: {org_id}")
        
        service = BillingService(session)
        
        try:
            intent = await service.create_payment_intent(
                organization_id=org_id,
                tier=SKUTier.PROFESSIONAL,
                billing_cycle=BillingCycle.MONTHLY,
                admin_email="admin@test.com",
                intelligence_addon=None,
                additional_users=0,
                callback_url="/payment/callback",
            )
            
            self.log_pass(f"Payment intent created: {intent.reference}")
            self.log_pass(f"Amount: ₦{intent.amount_naira:,}")
            self.log_pass(f"Authorization URL: {intent.authorization_url[:50]}...")
            
            # Check if PaymentTransaction was created in DB
            tx_result = await session.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.reference == intent.reference
                )
            )
            tx = tx_result.scalar_one_or_none()
            
            if tx:
                self.log_pass(f"PaymentTransaction record created: {tx.id}")
                self.log_pass(f"Transaction status: {tx.status}")
                if tx.amount_kobo == intent.amount_naira * 100:
                    self.log_pass("Amount kobo matches intent amount")
                else:
                    self.log_fail("Amount mismatch", f"TX: {tx.amount_kobo}, Intent: {intent.amount_naira * 100}")
            else:
                self.log_fail("PaymentTransaction", "Not found in database")
            
            # Rollback to not persist test data
            await session.rollback()
            self.log_pass("Test transaction rolled back")
            
        except Exception as e:
            self.log_fail("Payment intent creation", str(e))
            import traceback
            traceback.print_exc()
    
    async def test_exchange_rates_api(self, session):
        """Test 5: Exchange rates endpoint."""
        print("\n🔍 Test 5: Exchange Rates")
        
        result = await session.execute(text("SELECT COUNT(*) FROM exchange_rates"))
        count = result.scalar()
        
        if count > 0:
            self.log_pass(f"Exchange rates seeded: {count} rates")
            
            # Check currencies
            rates = await session.execute(text(
                "SELECT from_currency, to_currency, rate FROM exchange_rates"
            ))
            for row in rates.fetchall():
                self.log_pass(f"  Rate: {row[0]} → {row[1]} = {row[2]}")
        else:
            self.log_fail("Exchange rates", "No rates in database")
    
    async def test_api_endpoints(self):
        """Test 6: Test API endpoints via HTTP."""
        print("\n🔍 Test 6: API Endpoints (HTTP)")
        
        import httpx
        
        base_url = "http://localhost:5120"
        
        async with httpx.AsyncClient() as client:
            # Test pricing endpoint (no auth required)
            try:
                response = await client.get(f"{base_url}/api/v1/billing/pricing")
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) >= 3:
                        self.log_pass(f"GET /api/v1/billing/pricing: {len(data)} tiers")
                    else:
                        self.log_fail("/api/v1/billing/pricing", f"Unexpected response: {data}")
                else:
                    self.log_fail("/api/v1/billing/pricing", f"Status {response.status_code}")
            except Exception as e:
                self.log_fail("/api/v1/billing/pricing", str(e))
            
            # Test exchange rates endpoint (no auth required)
            try:
                response = await client.get(f"{base_url}/api/v1/billing/advanced/exchange-rates")
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get("rates", data)
                    self.log_pass(f"GET /api/v1/billing/advanced/exchange-rates: {len(rates)} rates")
                else:
                    self.log_fail("/api/v1/billing/advanced/exchange-rates", f"Status {response.status_code}")
            except Exception as e:
                self.log_fail("/api/v1/billing/advanced/exchange-rates", str(e))
            
            # Test checkout endpoint (requires auth - should return 401)
            try:
                response = await client.post(
                    f"{base_url}/api/v1/billing/checkout",
                    json={"tier": "professional", "billing_cycle": "monthly"}
                )
                if response.status_code == 401:
                    self.log_pass("POST /api/v1/billing/checkout: Correctly requires auth (401)")
                else:
                    self.log_fail("/api/v1/billing/checkout", f"Expected 401, got {response.status_code}")
            except Exception as e:
                self.log_fail("/api/v1/billing/checkout", str(e))
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        print(f"  ✅ Passed: {self.passed}")
        print(f"  ❌ Failed: {self.failed}")
        print(f"  📊 Total:  {self.passed + self.failed}")
        
        if self.errors:
            print("\n⚠️  Failures:")
            for error in self.errors:
                print(f"    - {error}")
        
        if self.failed == 0:
            print("\n🎉 All tests passed!")
        else:
            print(f"\n⚠️  {self.failed} test(s) failed - review above for details")


async def main():
    print("=" * 60)
    print("🔧 PAYSTACK CHECKOUT IMPLEMENTATION AUDIT")
    print("=" * 60)
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tester = CheckoutTester()
    
    async with async_session_maker() as session:
        await tester.test_database_schema(session)
        await tester.test_pricing_calculation(session)
        await tester.test_payment_provider(session)
        await tester.test_payment_intent_creation(session)
        await tester.test_exchange_rates_api(session)
    
    # Test HTTP endpoints separately
    await tester.test_api_endpoints()
    
    tester.print_summary()
    
    return tester.failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
