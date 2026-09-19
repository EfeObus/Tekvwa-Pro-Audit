"""Create a CORE tier tenant and test that enforcement works."""
import asyncio
from sqlalchemy import text
from app.database import async_session_maker
from app.services.feature_flags import FeatureFlagService, TIER_FEATURES
from app.models.sku import Feature, TenantSKU, SKUTier, IntelligenceAddon
from uuid import UUID

async def test():
    async with async_session_maker() as db:
        # Create a CORE tier tenant_sku for Tekvwa Demo
        demo_org_id = UUID('8d505426-5a31-4a57-84c5-87f4529685ac')
        
        # Check if already exists
        result = await db.execute(text('''
            SELECT id FROM tenant_skus WHERE organization_id = :org_id
        '''), {'org_id': str(demo_org_id)})
        existing = result.fetchone()
        
        if existing:
            print(f'Deleting existing tenant_sku for demo org...')
            await db.execute(text('''
                DELETE FROM tenant_skus WHERE organization_id = :org_id
            '''), {'org_id': str(demo_org_id)})
            await db.commit()
        
        # Create a CORE tier record
        print('Creating CORE tier tenant_sku for Tekvwa Demo...')
        sku = TenantSKU(
            organization_id=demo_org_id,
            tier=SKUTier.CORE,
            intelligence_addon=IntelligenceAddon.NONE,
            is_active=True,
        )
        db.add(sku)
        await db.commit()
        print(f'Created tenant_sku with tier={sku.tier}, intel={sku.intelligence_addon}')
        
        # Now test
        service = FeatureFlagService(db)
        service.clear_cache()
        
        print('\nTesting CORE tier enforcement:')
        tenant_sku = await service.get_tenant_sku(demo_org_id)
        print(f'  tenant_sku.tier: {tenant_sku.tier}')
        print(f'  tenant_sku.tier type: {type(tenant_sku.tier)}')
        
        effective_tier = await service.get_effective_tier(demo_org_id)
        print(f'  effective_tier: {effective_tier}')
        
        enabled = await service.get_enabled_features(demo_org_id)
        print(f'  enabled_features count: {len(enabled)}')
        
        # Check specific features
        test_features = [
            (Feature.GL_ENABLED, 'CORE'),
            (Feature.PAYROLL, 'PROFESSIONAL'),
            (Feature.WORM_VAULT, 'ENTERPRISE'),
            (Feature.MULTI_CURRENCY, 'PROFESSIONAL'),
            (Feature.BENFORDS_LAW, 'INTELLIGENCE'),
        ]
        
        print('\nFeature access test:')
        for f, expected_tier in test_features:
            has = await service.has_feature(demo_org_id, f)
            should_have = expected_tier == 'CORE'  # Only CORE features should be accessible
            correct = '✓' if has == should_have else '✗ WRONG!'
            print(f'  {f.value} ({expected_tier}): {has} {correct}')

if __name__ == '__main__':
    asyncio.run(test())
