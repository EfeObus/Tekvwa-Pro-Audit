"""Test SKU enforcement with a CORE tier org."""
import asyncio
from app.database import async_session_maker
from app.services.feature_flags import FeatureFlagService, TIER_FEATURES
from app.models.sku import Feature
from uuid import UUID

async def test():
    async with async_session_maker() as db:
        service = FeatureFlagService(db)
        
        # Test with Tekvwa Demo org (no tenant_sku record)
        demo_org_id = UUID('8d505426-5a31-4a57-84c5-87f4529685ac')
        
        print('Testing Tekvwa Demo org (no tenant_sku record):')
        tenant_sku = await service.get_tenant_sku(demo_org_id)
        print(f'  tenant_sku: {tenant_sku}')
        
        effective_tier = await service.get_effective_tier(demo_org_id)
        print(f'  effective_tier: {effective_tier}')
        
        enabled = await service.get_enabled_features(demo_org_id)
        print(f'  enabled_features count: {len(enabled)}')
        
        # Check specific features
        test_features = [
            (Feature.GL_ENABLED, 'CORE'),
            (Feature.PAYROLL, 'PROFESSIONAL'),
            (Feature.WORM_VAULT, 'ENTERPRISE'),
        ]
        for f, expected_tier in test_features:
            has = await service.has_feature(demo_org_id, f)
            correct = '✓' if (has and expected_tier == 'CORE') or (not has and expected_tier != 'CORE') else '✗ WRONG!'
            print(f'  {f.value} ({expected_tier}): {has} {correct}')

if __name__ == '__main__':
    asyncio.run(test())
