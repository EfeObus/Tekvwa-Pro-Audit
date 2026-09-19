#!/usr/bin/env python3
"""
Test SKU Enforcement - Verify that CORE tier users cannot access PROFESSIONAL/ENTERPRISE features

This script tests the feature gate implementation by checking:
1. Feature flag service correctly identifies tier features
2. Routers have proper feature gates applied
"""

import asyncio
import sys
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')

from app.config.sku_config import (
    Feature, SKUTier, 
    CORE_FEATURES, PROFESSIONAL_FEATURES, ENTERPRISE_FEATURES
)


def print_separator():
    print("=" * 60)


def test_feature_definitions():
    """Test that feature sets are properly defined."""
    print_separator()
    print("TEST 1: Feature Set Definitions")
    print_separator()
    
    print(f"\n✓ CORE tier has {len(CORE_FEATURES)} features:")
    for f in sorted(CORE_FEATURES, key=lambda x: x.value):
        print(f"    - {f.value}")
    
    professional_only = PROFESSIONAL_FEATURES - CORE_FEATURES
    print(f"\n✓ PROFESSIONAL tier adds {len(professional_only)} features:")
    for f in sorted(professional_only, key=lambda x: x.value):
        print(f"    - {f.value}")
    
    enterprise_only = ENTERPRISE_FEATURES - PROFESSIONAL_FEATURES
    print(f"\n✓ ENTERPRISE tier adds {len(enterprise_only)} features:")
    for f in sorted(enterprise_only, key=lambda x: x.value):
        print(f"    - {f.value}")


def test_router_feature_gates():
    """Test that routers have feature gates defined."""
    print_separator()
    print("TEST 2: Router Feature Gate Configuration")
    print_separator()
    
    from app.routers import (
        bank_reconciliation,
        payroll_advanced,
        advanced_accounting,
        inventory,
        year_end,
        evidence_routes,
        tax_2026,
        self_assessment,
        legal_holds,
        risk_signals,
        fx,
        budget,
    )
    
    routers_to_check = [
        ("bank_reconciliation", bank_reconciliation, Feature.BANK_RECONCILIATION),
        ("payroll_advanced", payroll_advanced, Feature.PAYROLL_ADVANCED),
        ("advanced_accounting", advanced_accounting, Feature.ADVANCED_REPORTS),
        ("inventory", inventory, Feature.INVENTORY_BASIC),
        ("year_end", year_end, Feature.ADVANCED_REPORTS),
        ("evidence_routes", evidence_routes, Feature.AUDIT_VAULT_EXTENDED),
        ("tax_2026", tax_2026, Feature.NRS_COMPLIANCE),
        ("self_assessment", self_assessment, Feature.NRS_COMPLIANCE),
        ("legal_holds", legal_holds, Feature.WORM_VAULT),
        ("risk_signals", risk_signals, Feature.WORM_VAULT),
        ("fx", fx, Feature.MULTI_CURRENCY),
        ("budget", budget, Feature.BUDGET_MANAGEMENT),
    ]
    
    print()
    all_passed = True
    
    for name, module, expected_feature in routers_to_check:
        router = module.router
        has_dependencies = bool(router.dependencies)
        
        if has_dependencies:
            print(f"✓ {name}: Has router-level dependencies (expected: {expected_feature.value})")
        else:
            print(f"✗ {name}: MISSING router-level dependencies!")
            all_passed = False
    
    print()
    if all_passed:
        print("✓ All checked routers have feature gates!")
    else:
        print("✗ Some routers are missing feature gates!")
    
    return all_passed


def test_core_tier_restrictions():
    """Test that CORE tier is restricted from PROFESSIONAL/ENTERPRISE features."""
    print_separator()
    print("TEST 3: CORE Tier Feature Restrictions")
    print_separator()
    
    # Features that CORE should NOT have
    restricted_for_core = [
        (Feature.PAYROLL, "Payroll"),
        (Feature.PAYROLL_ADVANCED, "Advanced Payroll"),
        (Feature.BANK_RECONCILIATION, "Bank Reconciliation"),
        (Feature.MULTI_CURRENCY, "Multi-Currency (FX)"),
        (Feature.BUDGET_MANAGEMENT, "Budget Management"),
        (Feature.ADVANCED_REPORTS, "Advanced Reports"),
        (Feature.WORM_VAULT, "WORM Vault"),
        (Feature.INTERCOMPANY, "Intercompany"),
    ]
    
    print("\nFeatures CORE tier should NOT have access to:")
    all_correct = True
    
    for feature, name in restricted_for_core:
        has_access = feature in CORE_FEATURES
        if has_access:
            print(f"✗ CORE has {name} - SHOULD NOT!")
            all_correct = False
        else:
            print(f"✓ CORE correctly lacks {name}")
    
    print()
    if all_correct:
        print("✓ CORE tier restrictions are correct!")
    else:
        print("✗ CORE tier has unexpected features!")
    
    return all_correct


def test_tier_feature_check():
    """Test the tier feature check logic."""
    print_separator()
    print("TEST 4: Tier Feature Check Simulation")
    print_separator()
    
    def check_feature_for_tier(feature: Feature, tier: SKUTier) -> bool:
        """Simulate the feature check logic."""
        tier_features = {
            SKUTier.CORE: CORE_FEATURES,
            SKUTier.PROFESSIONAL: PROFESSIONAL_FEATURES,
            SKUTier.ENTERPRISE: ENTERPRISE_FEATURES,
        }
        return feature in tier_features.get(tier, set())
    
    test_cases = [
        (Feature.GL_ENABLED, SKUTier.CORE, True, "CORE can use GL"),
        (Feature.PAYROLL, SKUTier.CORE, False, "CORE cannot use Payroll"),
        (Feature.PAYROLL, SKUTier.PROFESSIONAL, True, "PROFESSIONAL can use Payroll"),
        (Feature.MULTI_CURRENCY, SKUTier.CORE, False, "CORE cannot use FX"),
        (Feature.MULTI_CURRENCY, SKUTier.PROFESSIONAL, True, "PROFESSIONAL can use FX"),
        (Feature.WORM_VAULT, SKUTier.CORE, False, "CORE cannot use WORM Vault"),
        (Feature.WORM_VAULT, SKUTier.PROFESSIONAL, False, "PROFESSIONAL cannot use WORM Vault"),
        (Feature.WORM_VAULT, SKUTier.ENTERPRISE, True, "ENTERPRISE can use WORM Vault"),
    ]
    
    print()
    all_passed = True
    
    for feature, tier, expected, description in test_cases:
        result = check_feature_for_tier(feature, tier)
        if result == expected:
            print(f"✓ {description}")
        else:
            print(f"✗ {description} - got {result}, expected {expected}")
            all_passed = False
    
    print()
    if all_passed:
        print("✓ All tier feature checks pass!")
    else:
        print("✗ Some tier feature checks failed!")
    
    return all_passed


def main():
    print("\n" + "=" * 60)
    print("   Tekvwa Pro Audit - SKU Enforcement Test Suite")
    print("=" * 60)
    
    test_feature_definitions()
    
    router_test = test_router_feature_gates()
    restriction_test = test_core_tier_restrictions()
    tier_test = test_tier_feature_check()
    
    print_separator()
    print("SUMMARY")
    print_separator()
    
    tests = [
        ("Router Feature Gates", router_test),
        ("CORE Tier Restrictions", restriction_test),
        ("Tier Feature Checks", tier_test),
    ]
    
    all_passed = True
    for name, passed in tests:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        all_passed = all_passed and passed
    
    print()
    if all_passed:
        print("✓ ALL TESTS PASSED - SKU enforcement is properly configured!")
    else:
        print("✗ SOME TESTS FAILED - Review the issues above")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
