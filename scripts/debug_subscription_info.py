"""
Debug script to test the get_subscription_info method for Efe Obus organization.
This helps diagnose why the Settings page might show "Core" instead of "Enterprise".
"""
import asyncio
import sys
from uuid import UUID

# Add app directory to path
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

from sqlalchemy import select, and_
from app.database import async_session_factory
from app.models.sku import TenantSKU
from app.services.billing_service import BillingService


async def debug_subscription():
    """Debug the subscription info retrieval."""
    
    # Efe Obus organization ID
    org_id = UUID("b3345541-b9cf-4686-a41b-3fe4bf699bf3")
    
    print(f"=" * 60)
    print(f"DEBUGGING SUBSCRIPTION INFO FOR ORG: {org_id}")
    print(f"=" * 60)
    
    async with async_session_factory() as db:
        # Step 1: Direct query to TenantSKU
        print("\n[1] Direct TenantSKU query:")
        result = await db.execute(
            select(TenantSKU).where(
                and_(
                    TenantSKU.organization_id == org_id,
                    TenantSKU.is_active == True,
                )
            )
        )
        tenant_sku = result.scalar_one_or_none()
        
        if tenant_sku:
            print(f"    ✅ Found TenantSKU:")
            print(f"       - ID: {tenant_sku.id}")
            print(f"       - tier: {tenant_sku.tier} (type: {type(tenant_sku.tier)})")
            print(f"       - tier.value: {tenant_sku.tier.value if hasattr(tenant_sku.tier, 'value') else 'N/A'}")
            print(f"       - is_active: {tenant_sku.is_active}")
            print(f"       - is_trial property: {tenant_sku.is_trial}")
            print(f"       - trial_ends_at: {tenant_sku.trial_ends_at}")
            print(f"       - billing_cycle: {tenant_sku.billing_cycle}")
            print(f"       - current_period_start: {tenant_sku.current_period_start}")
            print(f"       - current_period_end: {tenant_sku.current_period_end}")
        else:
            print(f"    ❌ No active TenantSKU found!")
        
        # Step 2: Call BillingService.get_subscription_info
        print("\n[2] BillingService.get_subscription_info():")
        service = BillingService(db)
        
        try:
            info = await service.get_subscription_info(org_id)
            
            if info:
                print(f"    ✅ SubscriptionInfo returned:")
                print(f"       - tier: {info.tier} (type: {type(info.tier)})")
                print(f"       - tier.value: {info.tier.value if hasattr(info.tier, 'value') else 'N/A'}")
                print(f"       - billing_cycle: {info.billing_cycle}")
                print(f"       - status: {info.status}")
                print(f"       - is_trial: {info.is_trial}")
                print(f"       - trial_ends_at: {info.trial_ends_at}")
                print(f"       - current_period_start: {info.current_period_start}")
                print(f"       - current_period_end: {info.current_period_end}")
                print(f"       - amount_naira: {info.amount_naira}")
            else:
                print(f"    ❌ get_subscription_info() returned None!")
                print(f"       This would cause the API to return 'Core' as default!")
        except Exception as e:
            print(f"    ❌ Exception in get_subscription_info(): {e}")
            import traceback
            traceback.print_exc()
        
        # Step 3: Simulate the API tier_display mapping
        print("\n[3] API tier_display mapping simulation:")
        from app.models.sku import SKUTier
        
        tier_display_map = {
            SKUTier.CORE: "Core",
            SKUTier.PROFESSIONAL: "Professional",
            SKUTier.ENTERPRISE: "Enterprise",
        }
        
        if info:
            tier_display = tier_display_map.get(info.tier, "Core")
            print(f"    tier_display = {tier_display}")
        else:
            print(f"    Would default to 'Core' because info is None!")
    
    print(f"\n{'=' * 60}")
    print("DEBUG COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(debug_subscription())
