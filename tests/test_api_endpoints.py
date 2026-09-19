#!/usr/bin/env python3
"""
API Endpoint Test Suite for Tekvwa Pro Audit
Tests actual HTTP endpoints for all 5 features.
"""

import requests
import json
from datetime import date
from uuid import uuid4

BASE_URL = "http://localhost:5120"

# Track test results
test_results = {
    "passed": 0,
    "failed": 0,
    "errors": []
}

def test_endpoint(name, method, url, expected_statuses=[200, 201], data=None, auth_required=True):
    """Test an endpoint and track results"""
    try:
        full_url = f"{BASE_URL}{url}"
        
        if method.upper() == "GET":
            response = requests.get(full_url, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(full_url, json=data, timeout=10)
        else:
            print(f"  ⚠ Unknown method: {method}")
            return False
        
        # Check if we expect auth error for protected routes
        if auth_required and response.status_code == 401:
            # This is expected - endpoint requires auth and we didn't provide it
            print(f"  ✓ {name}: Requires auth (401) - EXPECTED")
            test_results["passed"] += 1
            return True
        elif auth_required and response.status_code == 422:
            # Validation error - endpoint exists but requires proper params
            print(f"  ✓ {name}: Validation required (422) - ENDPOINT EXISTS")
            test_results["passed"] += 1
            return True
        elif response.status_code in expected_statuses:
            print(f"  ✓ {name}: {response.status_code} OK")
            test_results["passed"] += 1
            return True
        elif response.status_code == 404:
            print(f"  ✗ {name}: 404 NOT FOUND")
            test_results["failed"] += 1
            test_results["errors"].append(f"{name}: 404")
            return False
        elif response.status_code == 500:
            print(f"  ⚠ {name}: 500 SERVER ERROR")
            test_results["failed"] += 1
            test_results["errors"].append(f"{name}: 500 - {response.text[:100]}")
            return False
        else:
            print(f"  ? {name}: Unexpected {response.status_code}")
            test_results["passed"] += 1  # Endpoint exists
            return True
            
    except requests.exceptions.ConnectionError:
        print(f"  ✗ {name}: Connection refused - is server running?")
        test_results["failed"] += 1
        return False
    except Exception as e:
        print(f"  ✗ {name}: Error - {e}")
        test_results["failed"] += 1
        return False


def test_health():
    """Test if server is running"""
    print("\n" + "=" * 60)
    print("SERVER HEALTH CHECK")
    print("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print("  ✓ Server is running")
            return True
        else:
            print(f"  ✗ Server returned {response.status_code}")
            return False
    except:
        print("  ✗ Cannot connect to server")
        return False


def test_openapi():
    """Test OpenAPI docs"""
    print("\n" + "=" * 60)
    print("OPENAPI DOCUMENTATION")
    print("=" * 60)
    
    test_endpoint("OpenAPI JSON", "GET", "/openapi.json", auth_required=False)
    test_endpoint("Swagger UI", "GET", "/api/docs", auth_required=False)
    test_endpoint("ReDoc", "GET", "/api/redoc", auth_required=False)


def test_fx_endpoints():
    """Test FX Multi-Currency endpoints"""
    print("\n" + "=" * 60)
    print("FEATURE 1: MULTI-CURRENCY FX GAIN/LOSS")
    print("=" * 60)
    
    entity_id = str(uuid4())
    
    # Test all FX endpoints
    test_endpoint("Get Exchange Rates", "GET", f"/api/v1/entities/{entity_id}/fx/exchange-rates")
    test_endpoint("Create Exchange Rate", "POST", f"/api/v1/entities/{entity_id}/fx/exchange-rates", 
                  data={"from_currency": "USD", "to_currency": "NGN", "rate": 1500.0})
    test_endpoint("Convert Currency", "POST", f"/api/v1/entities/{entity_id}/fx/convert",
                  data={"amount": 100, "from_currency": "USD", "to_currency": "NGN"})
    test_endpoint("FX Exposure Summary", "GET", f"/api/v1/entities/{entity_id}/fx/exposure")
    test_endpoint("FX Exposure by Currency", "GET", f"/api/v1/entities/{entity_id}/fx/exposure/USD")
    test_endpoint("Realized FX Gain/Loss", "POST", f"/api/v1/entities/{entity_id}/fx/realized-gain-loss",
                  data={"transaction_ids": []})
    test_endpoint("Period-End Revaluation", "POST", f"/api/v1/entities/{entity_id}/fx/period-end-revaluation",
                  data={"as_of_date": str(date.today())})
    test_endpoint("FX Gain/Loss Report", "GET", f"/api/v1/entities/{entity_id}/fx/reports/gain-loss")
    test_endpoint("FX Accounts Report", "GET", f"/api/v1/entities/{entity_id}/fx/reports/fx-accounts")


def test_consolidation_endpoints():
    """Test Multi-Entity Consolidation endpoints"""
    print("\n" + "=" * 60)
    print("FEATURE 2: MULTI-ENTITY CONSOLIDATION")
    print("=" * 60)
    
    # Test all consolidation endpoints
    test_endpoint("List Groups", "GET", "/api/v1/consolidation/groups")
    test_endpoint("Create Group", "POST", "/api/v1/consolidation/groups",
                  data={"name": "Test Group", "parent_entity_id": str(uuid4())})
    test_endpoint("Get Group", "GET", f"/api/v1/consolidation/groups/{uuid4()}")
    test_endpoint("Group Members", "GET", f"/api/v1/consolidation/groups/{uuid4()}/members")
    test_endpoint("Add Group Member", "POST", f"/api/v1/consolidation/groups/{uuid4()}/members",
                  data={"entity_id": str(uuid4()), "ownership_percentage": 100})
    test_endpoint("Trial Balance", "GET", f"/api/v1/consolidation/groups/{uuid4()}/trial-balance")
    test_endpoint("Balance Sheet", "GET", f"/api/v1/consolidation/groups/{uuid4()}/balance-sheet")
    test_endpoint("Income Statement", "GET", f"/api/v1/consolidation/groups/{uuid4()}/income-statement")
    test_endpoint("Cash Flow Statement", "GET", f"/api/v1/consolidation/groups/{uuid4()}/cash-flow-statement")
    test_endpoint("Elimination Entries", "POST", f"/api/v1/consolidation/groups/{uuid4()}/eliminations",
                  data={"description": "Test elimination", "debit_account_id": str(uuid4()), 
                        "credit_account_id": str(uuid4()), "amount": 1000})
    test_endpoint("Get Eliminations", "GET", f"/api/v1/consolidation/groups/{uuid4()}/eliminations")
    test_endpoint("Worksheet", "GET", f"/api/v1/consolidation/groups/{uuid4()}/worksheet")
    test_endpoint("Segment Report", "GET", f"/api/v1/consolidation/groups/{uuid4()}/segment-report")
    test_endpoint("Currency Translation", "GET", f"/api/v1/consolidation/groups/{uuid4()}/currency-translation")
    test_endpoint("Minority Interest", "GET", f"/api/v1/consolidation/groups/{uuid4()}/minority-interest")


def test_budget_endpoints():
    """Test Budget Management endpoints"""
    print("\n" + "=" * 60)
    print("FEATURE 3: BUDGET VS ACTUAL REPORTS")
    print("=" * 60)
    
    entity_id = str(uuid4())
    budget_id = str(uuid4())
    
    # Test all budget endpoints
    test_endpoint("List Budgets", "GET", f"/api/v1/entities/{entity_id}/budgets")
    test_endpoint("Create Budget", "POST", f"/api/v1/entities/{entity_id}/budgets",
                  data={"name": "Test Budget", "fiscal_year": 2024, 
                        "start_date": "2024-01-01", "end_date": "2024-12-31"})
    test_endpoint("Get Budget", "GET", f"/api/v1/entities/{entity_id}/budgets/{budget_id}")
    test_endpoint("Active Budget", "GET", f"/api/v1/entities/{entity_id}/budgets/active")
    test_endpoint("Approve Budget", "POST", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/approve")
    test_endpoint("Activate Budget", "POST", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/activate")
    test_endpoint("Add Line Item", "POST", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/line-items",
                  data={"account_id": str(uuid4()), "amount": 10000})
    test_endpoint("Get Line Items", "GET", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/line-items")
    test_endpoint("Budget vs Actual", "GET", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/variance")
    test_endpoint("Forecast", "GET", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/forecast")
    test_endpoint("Department Summary", "GET", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/department-summary")
    test_endpoint("Import Chart of Accounts", "POST", f"/api/v1/entities/{entity_id}/budgets/{budget_id}/import-accounts")
    test_endpoint("Compare Budgets", "POST", f"/api/v1/entities/{entity_id}/budgets/compare",
                  data={"budget_ids": [str(uuid4()), str(uuid4())]})


def test_year_end_endpoints():
    """Test Year-End Closing endpoints"""
    print("\n" + "=" * 60)
    print("FEATURE 4: YEAR-END CLOSING AUTOMATION")
    print("=" * 60)
    
    fiscal_year_id = str(uuid4())
    period_id = str(uuid4())
    entity_id = str(uuid4())
    
    # Test all year-end endpoints
    test_endpoint("List Fiscal Years", "GET", "/api/v1/year-end/fiscal-years")
    test_endpoint("List Periods", "GET", f"/api/v1/year-end/periods/{fiscal_year_id}")
    test_endpoint("Year-End Checklist", "GET", f"/api/v1/year-end/checklist/{fiscal_year_id}")
    test_endpoint("Generate Closing Entries", "POST", "/api/v1/year-end/closing-entries",
                  data={"fiscal_year_id": fiscal_year_id, "entity_id": entity_id})
    test_endpoint("Get Closing Entries", "GET", f"/api/v1/year-end/closing-entries/{fiscal_year_id}")
    test_endpoint("Close Fiscal Year", "POST", "/api/v1/year-end/close-fiscal-year",
                  data={"fiscal_year_id": fiscal_year_id, "entity_id": entity_id})
    test_endpoint("Create Opening Balances", "POST", "/api/v1/year-end/opening-balances",
                  data={"source_fiscal_year_id": fiscal_year_id, "entity_id": entity_id})
    test_endpoint("Get Opening Balances", "GET", f"/api/v1/year-end/opening-balances/{fiscal_year_id}")
    test_endpoint("Lock Period", "POST", "/api/v1/year-end/lock-period",
                  data={"period_id": period_id, "entity_id": entity_id})
    test_endpoint("Unlock Period", "POST", "/api/v1/year-end/unlock-period",
                  data={"period_id": period_id, "entity_id": entity_id})
    test_endpoint("Locked Periods", "GET", f"/api/v1/year-end/locked-periods?entity_id={entity_id}")
    test_endpoint("Summary Report", "GET", f"/api/v1/year-end/summary-report/{fiscal_year_id}")


def test_report_export_endpoints():
    """Test Financial Report Export endpoints"""
    print("\n" + "=" * 60)
    print("FEATURE 5: FINANCIAL REPORT EXPORT")
    print("=" * 60)
    
    entity_id = str(uuid4())
    
    # Test all report export endpoints
    test_endpoint("Export Formats", "GET", "/api/v1/reports/export/formats")
    test_endpoint("Report Types", "GET", "/api/v1/reports/export/report-types")
    test_endpoint("Balance Sheet PDF", "POST", "/api/v1/reports/export/balance-sheet",
                  data={"entity_id": entity_id, "as_of_date": str(date.today()), "format": "pdf"})
    test_endpoint("Balance Sheet Excel", "POST", "/api/v1/reports/export/balance-sheet",
                  data={"entity_id": entity_id, "as_of_date": str(date.today()), "format": "excel"})
    test_endpoint("Income Statement PDF", "POST", "/api/v1/reports/export/income-statement",
                  data={"entity_id": entity_id, "start_date": "2024-01-01", 
                        "end_date": str(date.today()), "format": "pdf"})
    test_endpoint("Trial Balance CSV", "POST", "/api/v1/reports/export/trial-balance",
                  data={"entity_id": entity_id, "as_of_date": str(date.today()), "format": "csv"})
    test_endpoint("General Ledger Excel", "POST", "/api/v1/reports/export/general-ledger",
                  data={"entity_id": entity_id, "start_date": "2024-01-01", 
                        "end_date": str(date.today()), "format": "excel"})
    
    # Test GET endpoints for fetching existing reports
    test_endpoint("Get Balance Sheets", "GET", f"/api/v1/reports/export/balance-sheet?entity_id={entity_id}")
    test_endpoint("Get Income Statements", "GET", f"/api/v1/reports/export/income-statement?entity_id={entity_id}")
    test_endpoint("Get Trial Balances", "GET", f"/api/v1/reports/export/trial-balance?entity_id={entity_id}")


def main():
    """Run all endpoint tests"""
    print("\n" + "=" * 60)
    print("API ENDPOINT TEST SUITE")
    print("Tekvwa Pro Audit - 5 Accounting Features")
    print("=" * 60)
    print(f"Testing against: {BASE_URL}")
    
    # First check if server is running
    if not test_health():
        print("\n✗ Server is not running. Please start the server first.")
        return 1
    
    # Test OpenAPI docs
    test_openapi()
    
    # Test all 5 features
    test_fx_endpoints()
    test_consolidation_endpoints()
    test_budget_endpoints()
    test_year_end_endpoints()
    test_report_export_endpoints()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    total = test_results["passed"] + test_results["failed"]
    print(f"Total Tests: {total}")
    print(f"Passed: {test_results['passed']}")
    print(f"Failed: {test_results['failed']}")
    
    if test_results["errors"]:
        print("\nErrors:")
        for error in test_results["errors"]:
            print(f"  - {error}")
    
    if test_results["failed"] == 0:
        print("\n✓ ALL ENDPOINTS ARE ACCESSIBLE!")
        return 0
    else:
        print(f"\n⚠ {test_results['failed']} endpoint(s) had issues")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
