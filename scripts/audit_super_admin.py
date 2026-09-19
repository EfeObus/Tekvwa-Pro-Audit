#!/usr/bin/env python3
"""
Super Admin Dashboard - Full Audit Report
Tests all implemented admin endpoints
"""
import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:5120/api/v1"

def main():
    # Login
    login_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "info@tekvwa.org",
        "password": "SuperAdmin@TekVwarho2026!"
    })
    token = login_resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("=" * 70)
    print("SUPER ADMIN DASHBOARD - FULL AUDIT REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print("")

    results = {}
    
    # Define all endpoints to test
    modules = {
        "IMPL-001: Emergency Controls": [
            ("GET", "/admin/emergency/status", "Platform status"),
            ("GET", "/admin/emergency/stats", "Emergency statistics"),
            ("GET", "/admin/emergency/features", "Available features"),
            ("GET", "/admin/emergency/tenant/suspended", "Suspended tenants"),
            ("GET", "/admin/emergency/history", "Emergency history"),
            ("GET", "/admin/emergency/active", "Active controls"),
        ],
        "IMPL-002: Cross-Tenant User Search": [
            ("GET", "/admin/users/search", "Search users"),
            ("GET", "/admin/users/search?query=admin", "Search with query"),
            ("GET", "/admin/users/c7492f03-c20c-41da-938e-7c922ce60e3d", "User details"),
            ("GET", "/admin/users/c7492f03-c20c-41da-938e-7c922ce60e3d/activity", "User activity"),
        ],
        "IMPL-003: Platform Staff Management": [
            ("GET", "/admin/staff/list", "List platform staff"),
            ("GET", "/admin/staff/stats", "Staff statistics"),
            ("GET", "/admin/staff/c7492f03-c20c-41da-938e-7c922ce60e3d", "Get staff details"),
            ("GET", "/admin/staff/c7492f03-c20c-41da-938e-7c922ce60e3d/audit", "Staff audit trail"),
        ],
        "IMPL-004: Organization Verification": [
            ("GET", "/admin/verifications/stats", "Verification statistics"),
            ("GET", "/admin/verifications", "List organizations"),
            ("GET", "/admin/verifications/b3345541-b9cf-4686-a41b-3fe4bf699bf3", "Organization details"),
            ("GET", "/admin/verifications/b3345541-b9cf-4686-a41b-3fe4bf699bf3/history", "Verification history"),
        ],
        "IMPL-005: Global Audit Log Viewer": [
            ("GET", "/admin/audit-logs/stats", "Audit log statistics"),
            ("GET", "/admin/audit-logs", "Search audit logs"),
            ("GET", "/admin/audit-logs/filters/actions", "Filter options - actions"),
            ("GET", "/admin/audit-logs/filters/entity-types", "Filter options - entity types"),
        ],
        "IMPL-006: Platform Health Metrics": [
            ("GET", "/admin/health/overview", "Health overview"),
            ("GET", "/admin/health/system", "System health"),
            ("GET", "/admin/health/security", "Security metrics"),
            ("GET", "/admin/health/organizations", "Organization health"),
            ("GET", "/admin/health/trends", "Usage trends"),
            ("GET", "/admin/health/feature-usage", "Feature usage"),
        ],
        "OTHER: Admin Routers": [
            ("GET", "/admin/tenants", "List tenants"),
            ("GET", "/admin/tenants/stats", "Tenant statistics"),
            ("GET", "/admin/tenants/b3345541-b9cf-4686-a41b-3fe4bf699bf3", "Tenant details"),
        ],
    }
    
    total_passed = 0
    total_failed = 0
    
    for module_name, endpoints in modules.items():
        print("-" * 70)
        print(module_name)
        print("-" * 70)
        
        module_passed = 0
        module_failed = 0
        
        for method, endpoint, desc in endpoints:
            try:
                if method == "GET":
                    resp = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=5)
                elif method == "POST":
                    resp = requests.post(f"{BASE_URL}{endpoint}", headers=headers, timeout=5)
                
                if resp.status_code == 200:
                    print(f"  PASS | {method} {endpoint} - {desc}")
                    module_passed += 1
                else:
                    print(f"  FAIL ({resp.status_code}) | {method} {endpoint} - {desc}")
                    module_failed += 1
            except Exception as e:
                print(f"  ERROR | {method} {endpoint} - {str(e)[:50]}")
                module_failed += 1
        
        total_passed += module_passed
        total_failed += module_failed
        results[module_name] = (module_passed, module_failed)
        print("")
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for module_name, (passed, failed) in results.items():
        total = passed + failed
        status = "PASS" if failed == 0 else "PARTIAL" if passed > 0 else "FAIL"
        print(f"  [{status}] {module_name}: {passed}/{total}")
    
    print("")
    total = total_passed + total_failed
    print(f"  TOTAL: {total_passed}/{total} endpoints passing")
    print(f"  Pass rate: {100 * total_passed / total:.1f}%")
    
    return total_failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
