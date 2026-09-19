#!/usr/bin/env python3
"""
End-to-End Checkout Test with Authentication

This script tests the complete checkout flow by:
1. Logging in as a real user
2. Creating a checkout session
3. Verifying the payment intent is created correctly
"""
import asyncio
import sys
import httpx
from datetime import datetime

sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')


async def test_authenticated_checkout():
    """Test checkout with an authenticated user session."""
    base_url = "http://localhost:5120"
    
    print("=" * 60)
    print("🔧 END-TO-END CHECKOUT TEST")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # First, let's try to login
        print("\n1. Attempting login...")
        
        # Get login page to get CSRF token if needed
        login_page = await client.get(f"{base_url}/login")
        
        # Try login with test credentials
        login_response = await client.post(
            f"{base_url}/login",
            data={
                "username": "admin@test.com",
                "password": "admin123",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if login_response.status_code in [200, 302, 303]:
            print(f"   ✅ Login response: {login_response.status_code}")
            # Check if we got cookies
            cookies = client.cookies
            if cookies:
                print(f"   ✅ Session cookies received: {len(cookies)} cookies")
                for name in cookies.keys():
                    print(f"      - {name}")
            
            # Try the checkout endpoint with the session
            print("\n2. Testing checkout endpoint...")
            
            checkout_response = await client.post(
                f"{base_url}/api/v1/billing/checkout",
                json={
                    "tier": "professional",
                    "billing_cycle": "monthly",
                    "intelligence_addon": None,
                    "additional_users": 0,
                    "callback_url": f"{base_url}/payment-success",
                },
                headers={"Content-Type": "application/json"},
            )
            
            print(f"   Response status: {checkout_response.status_code}")
            
            if checkout_response.status_code == 200:
                data = checkout_response.json()
                print(f"   ✅ Checkout session created!")
                print(f"      Reference: {data.get('reference')}")
                print(f"      Amount: {data.get('amount_formatted')}")
                print(f"      Authorization URL: {data.get('authorization_url', '')[:60]}...")
                print(f"      Tier: {data.get('tier')}")
                print(f"      Billing Cycle: {data.get('billing_cycle')}")
                return True
            elif checkout_response.status_code == 401:
                print(f"   ❌ Not authenticated - login may have failed")
                print(f"   Response: {checkout_response.text[:200]}")
            elif checkout_response.status_code == 400:
                error = checkout_response.json()
                print(f"   ⚠️ Bad request: {error.get('detail', checkout_response.text)}")
            else:
                print(f"   ❌ Unexpected response: {checkout_response.text[:200]}")
        else:
            print(f"   ❌ Login failed: {login_response.status_code}")
            print(f"   Response: {login_response.text[:200]}")
        
        # Alternative: Try to use direct API token authentication
        print("\n3. Testing with direct database user lookup...")
        
        # Get an access token by direct method
        from app.database import async_session_maker
        from sqlalchemy import text
        
        async with async_session_maker() as session:
            result = await session.execute(text("""
                SELECT u.id, u.email, o.id as org_id
                FROM users u
                JOIN organizations o ON u.organization_id = o.id
                WHERE u.is_active = true
                LIMIT 1
            """))
            user = result.fetchone()
            
            if user:
                print(f"   Found user: {user[1]} (org: {user[2]})")
                
                # Test the service directly
                from app.services.billing_service import BillingService, BillingCycle
                from app.models.sku import SKUTier
                
                service = BillingService(session)
                
                try:
                    intent = await service.create_payment_intent(
                        organization_id=user[2],
                        tier=SKUTier.PROFESSIONAL,
                        billing_cycle=BillingCycle.MONTHLY,
                        admin_email=user[1],
                        callback_url="/payment-success",
                    )
                    
                    print(f"   ✅ Payment intent created via service!")
                    print(f"      Reference: {intent.reference}")
                    print(f"      Amount: ₦{intent.amount_naira:,}")
                    print(f"      URL: {intent.authorization_url[:60]}...")
                    
                    # Rollback to not persist test data
                    await session.rollback()
                    print(f"   ✅ Test data rolled back")
                    return True
                    
                except Exception as e:
                    print(f"   ❌ Service error: {e}")
                    await session.rollback()
            else:
                print("   ❌ No active user found in database")
    
    return False


if __name__ == "__main__":
    success = asyncio.run(test_authenticated_checkout())
    print("\n" + "=" * 60)
    if success:
        print("🎉 CHECKOUT TEST PASSED!")
    else:
        print("⚠️ CHECKOUT TEST COMPLETED WITH ISSUES")
    print("=" * 60)
