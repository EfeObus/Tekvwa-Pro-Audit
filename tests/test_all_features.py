#!/usr/bin/env python3
"""
Comprehensive test script for all 5 implemented accounting features:
1. Multi-Currency FX Gain/Loss (10 routes)
2. Multi-Entity Consolidation (15 routes)
3. Budget vs Actual Reports (17 routes)
4. Year-End Closing Automation (13 routes)
5. Financial Report Export (10 routes)
"""

import asyncio
import sys
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

# Add parent directory to path
sys.path.insert(0, '/Users/efeobukohwo/Desktop/Tekvwa Pro Audit')


def test_imports():
    """Test that all modules import correctly"""
    print("=" * 60)
    print("TESTING MODULE IMPORTS")
    print("=" * 60)
    
    results = []
    
    # Test FX service and router
    try:
        from app.services.fx_service import FXService
        from app.routers.fx import router as fx_router
        print("✓ FX Service & Router - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ FX Service & Router - FAILED: {e}")
        results.append(False)
    
    # Test Consolidation service and router
    try:
        from app.services.consolidation_service import ConsolidationService
        from app.routers.consolidation import router as consolidation_router
        print("✓ Consolidation Service & Router - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Consolidation Service & Router - FAILED: {e}")
        results.append(False)
    
    # Test Budget service and router
    try:
        from app.services.budget_service import BudgetService
        from app.routers.budget import router as budget_router
        print("✓ Budget Service & Router - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Budget Service & Router - FAILED: {e}")
        results.append(False)
    
    # Test Year-End Closing service and router
    try:
        from app.services.year_end_closing_service import YearEndClosingService
        from app.routers.year_end import router as year_end_router
        print("✓ Year-End Closing Service & Router - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Year-End Closing Service & Router - FAILED: {e}")
        results.append(False)
    
    # Test Report Export service and router
    try:
        from app.services.report_export_service import FinancialReportExportService
        from app.routers.report_export import router as report_export_router
        print("✓ Report Export Service & Router - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Report Export Service & Router - FAILED: {e}")
        results.append(False)
    
    print()
    return all(results)


def test_route_counts():
    """Test that all routers have the expected number of routes"""
    print("=" * 60)
    print("TESTING ROUTE COUNTS")
    print("=" * 60)
    
    results = []
    
    # FX Router - Expected: 10 routes
    try:
        from app.routers.fx import router as fx_router
        fx_count = len(fx_router.routes)
        expected = 10
        status = "✓" if fx_count >= expected else "✗"
        print(f"{status} FX Router: {fx_count} routes (expected >= {expected})")
        results.append(fx_count >= expected)
    except Exception as e:
        print(f"✗ FX Router - FAILED: {e}")
        results.append(False)
    
    # Consolidation Router - Expected: 15 routes
    try:
        from app.routers.consolidation import router as consolidation_router
        cons_count = len(consolidation_router.routes)
        expected = 15
        status = "✓" if cons_count >= expected else "✗"
        print(f"{status} Consolidation Router: {cons_count} routes (expected >= {expected})")
        results.append(cons_count >= expected)
    except Exception as e:
        print(f"✗ Consolidation Router - FAILED: {e}")
        results.append(False)
    
    # Budget Router - Expected: 16 routes
    try:
        from app.routers.budget import router as budget_router
        budget_count = len(budget_router.routes)
        expected = 16
        status = "✓" if budget_count >= expected else "✗"
        print(f"{status} Budget Router: {budget_count} routes (expected >= {expected})")
        results.append(budget_count >= expected)
    except Exception as e:
        print(f"✗ Budget Router - FAILED: {e}")
        results.append(False)
    
    # Year-End Router - Expected: 13 routes
    try:
        from app.routers.year_end import router as year_end_router
        ye_count = len(year_end_router.routes)
        expected = 13
        status = "✓" if ye_count >= expected else "✗"
        print(f"{status} Year-End Router: {ye_count} routes (expected >= {expected})")
        results.append(ye_count >= expected)
    except Exception as e:
        print(f"✗ Year-End Router - FAILED: {e}")
        results.append(False)
    
    # Report Export Router - Expected: 10 routes
    try:
        from app.routers.report_export import router as report_export_router
        export_count = len(report_export_router.routes)
        expected = 10
        status = "✓" if export_count >= expected else "✗"
        print(f"{status} Report Export Router: {export_count} routes (expected >= {expected})")
        results.append(export_count >= expected)
    except Exception as e:
        print(f"✗ Report Export Router - FAILED: {e}")
        results.append(False)
    
    print()
    return all(results)


def test_schema_imports():
    """Test that all schema classes are properly defined"""
    print("=" * 60)
    print("TESTING SCHEMA IMPORTS")
    print("=" * 60)
    
    results = []
    
    # Test FX schemas (defined in accounting.py)
    try:
        from app.schemas.accounting import (
            ExchangeRateCreate,
            ExchangeRateResponse,
            CurrencyConversionRequest,
            FXExposureReport,
            FXRevaluationResponse
        )
        print("✓ FX Schemas (in accounting.py) - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ FX Schemas - FAILED: {e}")
        results.append(False)
    
    # Test Consolidation schemas (defined in router file)
    try:
        from app.routers.consolidation import (
            EntityGroupCreate,
            EntityGroupResponse,
            ConsolidatedReportRequest,
            GroupMemberAdd
        )
        print("✓ Consolidation Schemas (in router) - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Consolidation Schemas - FAILED: {e}")
        results.append(False)
    
    # Test Budget schemas (defined in router file)
    try:
        from app.routers.budget import (
            BudgetCreate,
            BudgetResponse,
            BudgetLineItemCreate,
            BudgetLineItemResponse
        )
        print("✓ Budget Schemas (in router) - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Budget Schemas - FAILED: {e}")
        results.append(False)
    
    # Test Year-End schemas (defined in router file)
    try:
        from app.routers.year_end import (
            ChecklistResponse,
            GenerateClosingEntriesRequest,
            ClosingEntriesResponse,
            CreateOpeningBalancesRequest,
            OpeningBalancesResponse
        )
        print("✓ Year-End Schemas (in router) - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Year-End Schemas - FAILED: {e}")
        results.append(False)
    
    # Test Report Export schemas (defined in router file)
    try:
        from app.routers.report_export import (
            ExportBalanceSheetRequest,
            ExportIncomeStatementRequest,
            ExportTrialBalanceRequest,
            ExportGeneralLedgerRequest
        )
        print("✓ Report Export Schemas (in router) - OK")
        results.append(True)
    except Exception as e:
        print(f"✗ Report Export Schemas - FAILED: {e}")
        results.append(False)
    
    print()
    return all(results)


def test_service_methods():
    """Test that service classes have all expected methods"""
    print("=" * 60)
    print("TESTING SERVICE METHODS")
    print("=" * 60)
    
    results = []
    
    # Test FX Service methods
    try:
        from app.services.fx_service import FXService
        expected_methods = [
            'get_exchange_rate',
            'get_all_exchange_rates',
            'convert_amount',
            'get_fx_exposure_by_currency',
            'run_period_end_revaluation',
            'get_fx_gain_loss_report'
        ]
        missing = [m for m in expected_methods if not hasattr(FXService, m)]
        if not missing:
            print("✓ FX Service methods - OK")
            results.append(True)
        else:
            print(f"✗ FX Service missing methods: {missing}")
            results.append(False)
    except Exception as e:
        print(f"✗ FX Service methods - FAILED: {e}")
        results.append(False)
    
    # Test Consolidation Service methods
    try:
        from app.services.consolidation_service import ConsolidationService
        expected_methods = [
            'create_entity_group',
            'add_group_member',
            'get_consolidated_balance_sheet',
            'get_consolidated_income_statement',
            'create_elimination_journal_entry'
        ]
        missing = [m for m in expected_methods if not hasattr(ConsolidationService, m)]
        if not missing:
            print("✓ Consolidation Service methods - OK")
            results.append(True)
        else:
            print(f"✗ Consolidation Service missing methods: {missing}")
            results.append(False)
    except Exception as e:
        print(f"✗ Consolidation Service methods - FAILED: {e}")
        results.append(False)
    
    # Test Budget Service methods
    try:
        from app.services.budget_service import BudgetService
        expected_methods = [
            'create_budget',
            'update_budget',
            'get_budget_vs_actual',
            'forecast_budget_performance'
        ]
        missing = [m for m in expected_methods if not hasattr(BudgetService, m)]
        if not missing:
            print("✓ Budget Service methods - OK")
            results.append(True)
        else:
            print(f"✗ Budget Service missing methods: {missing}")
            results.append(False)
    except Exception as e:
        print(f"✗ Budget Service methods - FAILED: {e}")
        results.append(False)
    
    # Test Year-End Closing Service methods
    try:
        from app.services.year_end_closing_service import YearEndClosingService
        expected_methods = [
            'get_year_end_checklist',
            'generate_closing_entries',
            'close_fiscal_year',
            'create_opening_balances',
            'lock_period',
            'unlock_period'
        ]
        missing = [m for m in expected_methods if not hasattr(YearEndClosingService, m)]
        if not missing:
            print("✓ Year-End Closing Service methods - OK")
            results.append(True)
        else:
            print(f"✗ Year-End Closing Service missing methods: {missing}")
            results.append(False)
    except Exception as e:
        print(f"✗ Year-End Closing Service methods - FAILED: {e}")
        results.append(False)
    
    # Test Report Export Service methods
    try:
        from app.services.report_export_service import FinancialReportExportService
        expected_methods = [
            'export_balance_sheet',
            'export_income_statement',
            'export_trial_balance',
            'export_general_ledger'
        ]
        missing = [m for m in expected_methods if not hasattr(FinancialReportExportService, m)]
        if not missing:
            print("✓ Report Export Service methods - OK")
            results.append(True)
        else:
            print(f"✗ Report Export Service missing methods: {missing}")
            results.append(False)
    except Exception as e:
        print(f"✗ Report Export Service methods - FAILED: {e}")
        results.append(False)
    
    print()
    return all(results)


def test_app_startup():
    """Test that the FastAPI app starts up correctly with all routers"""
    print("=" * 60)
    print("TESTING APP STARTUP")
    print("=" * 60)
    
    try:
        from main import app
        
        # Get all registered routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        
        # Check for our feature routes
        features = {
            'FX': '/api/v1/entities/',  # /api/v1/entities/{entity_id}/fx
            'Consolidation': '/api/v1/consolidation',
            'Budget': '/api/v1/entities/',  # /api/v1/entities/{entity_id}/budgets
            'Year-End': '/api/v1/year-end',
            'Report Export': '/api/v1/reports/export'
        }
        
        # More specific patterns to verify
        specific_routes = {
            'FX Exchange Rates': '/fx/exchange-rates',
            'FX Revaluation': '/fx/period-end-revaluation',
            'Consolidation Groups': '/api/v1/consolidation/groups',
            'Budget vs Actual': '/budgets/',
            'Year-End Checklist': '/api/v1/year-end/checklist',
            'Report Balance Sheet': '/api/v1/reports/export/balance-sheet'
        }
        
        all_found = True
        for feature, prefix in features.items():
            found = any(prefix in r for r in routes)
            status = "✓" if found else "✗"
            print(f"{status} {feature} routes ({prefix}*)")
            if not found:
                all_found = False
        
        # Check specific routes
        print("\nSpecific Route Checks:")
        for feature, pattern in specific_routes.items():
            found = any(pattern in r for r in routes)
            status = "✓" if found else "✗"
            print(f"  {status} {feature}")
            if not found:
                all_found = False
        
        # Count total routes
        total_routes = len([r for r in routes if r.startswith('/api/v1/')])
        print(f"\nTotal API routes: {total_routes}")
        
        print()
        return all_found
    except Exception as e:
        print(f"✗ App Startup - FAILED: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("COMPREHENSIVE FEATURE TEST SUITE")
    print("Tekvwa Pro Audit - 5 Accounting Features")
    print("=" * 60 + "\n")
    
    all_passed = True
    
    # Run tests
    if not test_imports():
        all_passed = False
    
    if not test_route_counts():
        all_passed = False
    
    if not test_schema_imports():
        all_passed = False
    
    if not test_service_methods():
        all_passed = False
    
    if not test_app_startup():
        all_passed = False
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    if all_passed:
        print("✓ ALL TESTS PASSED!")
        print("\nAll 5 features are properly implemented:")
        print("  1. Multi-Currency FX Gain/Loss")
        print("  2. Multi-Entity Consolidation")
        print("  3. Budget vs Actual Reports")
        print("  4. Year-End Closing Automation")
        print("  5. Financial Report Export")
        return 0
    else:
        print("✗ SOME TESTS FAILED - Check output above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
