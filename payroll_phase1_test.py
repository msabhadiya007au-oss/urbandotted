#!/usr/bin/env python3
"""
PAYROLL PHASE 1 VERIFICATION TEST SUITE

Tests:
- NEW PAYROLL ENDPOINTS (A-J)
- BUSINESS-ID ISOLATION (K)
- REGRESSION SMOKE (L)

Test credentials: urbandottedstore@gmail.com / Milan@112233!@#
"""
import requests
import json
import sys
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://deploy-fix-145.preview.emergentagent.com/api"
EMAIL = "urbandottedstore@gmail.com"
PASSWORD = "Milan@112233!@#"

# Test results tracking
results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_pass(test_name):
    print(f"✅ PASS: {test_name}")
    results["passed"].append(test_name)

def log_fail(test_name, reason):
    print(f"❌ FAIL: {test_name}")
    print(f"   Reason: {reason}")
    results["failed"].append({"test": test_name, "reason": reason})

def log_warning(test_name, message):
    print(f"⚠️  WARNING: {test_name}")
    print(f"   Message: {message}")
    results["warnings"].append({"test": test_name, "message": message})

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

# Session for cookies
session = requests.Session()

def login():
    """Login and get auth cookies"""
    print_section("AUTHENTICATION")
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD
    })
    if resp.status_code != 200:
        log_fail("Login", f"Status {resp.status_code}: {resp.text}")
        sys.exit(1)
    
    data = resp.json()
    if not data.get("user_id"):
        log_fail("Login", "No user_id in response")
        sys.exit(1)
    
    log_pass("Login with test credentials")
    return data

def test_payroll_status():
    """A. GET /api/payroll/status → 200"""
    print_section("A. PAYROLL STATUS ENDPOINT")
    resp = session.get(f"{BASE_URL}/payroll/status")
    
    if resp.status_code != 200:
        log_fail("GET /payroll/status", f"Status {resp.status_code}: {resp.text}")
        return
    
    data = resp.json()
    
    # Verify structure
    required_keys = ["stp", "payg", "super", "email", "employer_configured"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        log_fail("GET /payroll/status", f"Missing keys: {missing}")
        return
    
    # Verify STP
    if data["stp"].get("enabled") != False or data["stp"].get("status") != "NOT CONNECTED":
        log_fail("GET /payroll/status", f"STP should be disabled/NOT CONNECTED, got: {data['stp']}")
        return
    
    # Verify PAYG
    if data["payg"].get("mode") != "manual":
        log_fail("GET /payroll/status", f"PAYG mode should be 'manual', got: {data['payg']}")
        return
    
    # Verify Super
    if data["super"].get("mode") != "tracked":
        log_fail("GET /payroll/status", f"Super mode should be 'tracked', got: {data['super']}")
        return
    
    # Verify Email
    if data["email"].get("enabled") != False:
        log_fail("GET /payroll/status", f"Email should be disabled, got: {data['email']}")
        return
    
    log_pass("GET /payroll/status - correct structure and values")

def test_employer_profile():
    """B. Employer profile CRUD"""
    print_section("B. EMPLOYER PROFILE")
    
    # GET (may be empty initially)
    resp = session.get(f"{BASE_URL}/payroll/employer")
    if resp.status_code != 200:
        log_fail("GET /payroll/employer", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass("GET /payroll/employer - 200 OK")
    
    # PUT with valid data
    employer_data = {
        "legal_business_name": "Urban Dotted Pty Ltd",
        "abn": "12345678901",
        "default_pay_frequency": "fortnightly",
        "default_super_rate": "0.12"
    }
    resp = session.put(f"{BASE_URL}/payroll/employer", json=employer_data)
    if resp.status_code != 200:
        log_fail("PUT /payroll/employer", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass("PUT /payroll/employer - saved successfully")
    
    # GET again to verify
    resp = session.get(f"{BASE_URL}/payroll/employer")
    if resp.status_code != 200:
        log_fail("GET /payroll/employer (verify)", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if data.get("legal_business_name") != "Urban Dotted Pty Ltd":
        log_fail("GET /payroll/employer (verify)", f"legal_business_name mismatch: {data.get('legal_business_name')}")
        return
    if data.get("default_pay_frequency") != "fortnightly":
        log_fail("GET /payroll/employer (verify)", f"default_pay_frequency mismatch: {data.get('default_pay_frequency')}")
        return
    log_pass("GET /payroll/employer - values persisted correctly")
    
    # PUT with invalid pay_frequency
    invalid_data = {
        "legal_business_name": "Test",
        "default_pay_frequency": "annual"  # Invalid
    }
    resp = session.put(f"{BASE_URL}/payroll/employer", json=invalid_data)
    if resp.status_code != 422:
        log_fail("PUT /payroll/employer (invalid)", f"Expected 422, got {resp.status_code}")
        return
    log_pass("PUT /payroll/employer - correctly rejects invalid pay_frequency")

def test_fy_dropdown():
    """C. FY dropdown fix"""
    print_section("C. FY DROPDOWN FIX")
    
    resp = session.get(f"{BASE_URL}/meta")
    if resp.status_code != 200:
        log_fail("GET /meta", f"Status {resp.status_code}: {resp.text}")
        return
    
    data = resp.json()
    
    if "fy_options" not in data:
        log_fail("GET /meta", "Missing fy_options")
        return
    
    if "current_fy" not in data:
        log_fail("GET /meta", "Missing current_fy")
        return
    
    fy_options = data["fy_options"]
    current_fy = data["current_fy"]
    
    # Verify first entry is current FY
    if fy_options[0] != current_fy:
        log_fail("GET /meta", f"First FY option should be current_fy. Got: {fy_options[0]}, expected: {current_fy}")
        return
    
    # Verify no future FY (extract year from FY2026-27 format)
    current_year = int(current_fy.replace("FY", "").split("-")[0])
    for fy in fy_options:
        fy_year = int(fy.replace("FY", "").split("-")[0])
        if fy_year > current_year:
            log_fail("GET /meta", f"Future FY detected: {fy} (current: {current_fy})")
            return
    
    # Verify 8 entries (default)
    if len(fy_options) != 8:
        log_warning("GET /meta", f"Expected 8 FY options, got {len(fy_options)}")
    
    log_pass("GET /meta - FY dropdown correct (no future FYs, current FY first)")

def test_employees_crud():
    """D. Employees CRUD"""
    print_section("D. EMPLOYEES CRUD")
    
    # POST - Create employee
    employee_data = {
        "first_name": "Test",
        "last_name": "Employee",
        "employment_type": "casual"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees", json=employee_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees", f"Status {resp.status_code}: {resp.text}")
        return
    
    emp = resp.json()
    if not emp.get("employee_id", "").startswith("emp_"):
        log_fail("POST /payroll/employees", f"employee_id should start with 'emp_', got: {emp.get('employee_id')}")
        return
    
    employee_id = emp["employee_id"]
    log_pass(f"POST /payroll/employees - created {employee_id}")
    
    # GET list - should contain our employee
    resp = session.get(f"{BASE_URL}/payroll/employees")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if "items" not in data:
        log_fail("GET /payroll/employees", "Missing 'items' in response")
        return
    
    found = any(e.get("employee_id") == employee_id for e in data["items"])
    if not found:
        log_fail("GET /payroll/employees", f"Employee {employee_id} not in list")
        return
    log_pass("GET /payroll/employees - employee in list")
    
    # GET single
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}")
    if resp.status_code != 200:
        log_fail(f"GET /payroll/employees/{employee_id}", f"Status {resp.status_code}")
        return
    log_pass(f"GET /payroll/employees/{employee_id} - 200 OK")
    
    # PUT - Update
    update_data = {**employee_data, "job_title": "Test Manager"}
    resp = session.put(f"{BASE_URL}/payroll/employees/{employee_id}", json=update_data)
    if resp.status_code != 200:
        log_fail(f"PUT /payroll/employees/{employee_id}", f"Status {resp.status_code}")
        return
    
    updated = resp.json()
    if updated.get("job_title") != "Test Manager":
        log_fail(f"PUT /payroll/employees/{employee_id}", f"job_title not updated: {updated.get('job_title')}")
        return
    log_pass(f"PUT /payroll/employees/{employee_id} - updated successfully")
    
    # GET with search query
    resp = session.get(f"{BASE_URL}/payroll/employees?q=Test")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees?q=Test", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    found = any(e.get("employee_id") == employee_id for e in data.get("items", []))
    if not found:
        log_fail("GET /payroll/employees?q=Test", "Search didn't find employee")
        return
    log_pass("GET /payroll/employees?q=Test - search working")
    
    # GET with status=archived (should be empty before delete)
    resp = session.get(f"{BASE_URL}/payroll/employees?status=archived")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees?status=archived", f"Status {resp.status_code}")
        return
    log_pass("GET /payroll/employees?status=archived - 200 OK")
    
    # DELETE (soft delete)
    resp = session.delete(f"{BASE_URL}/payroll/employees/{employee_id}")
    if resp.status_code != 200:
        log_fail(f"DELETE /payroll/employees/{employee_id}", f"Status {resp.status_code}")
        return
    log_pass(f"DELETE /payroll/employees/{employee_id} - soft deleted")
    
    # Verify soft delete - should not appear in default list
    resp = session.get(f"{BASE_URL}/payroll/employees")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees (after delete)", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    found = any(e.get("employee_id") == employee_id for e in data.get("items", []))
    if found:
        log_fail("GET /payroll/employees (after delete)", "Deleted employee still in default list")
        return
    log_pass("GET /payroll/employees (after delete) - employee excluded from default list")
    
    return employee_id

def test_pay_settings_history():
    """E. Pay settings history"""
    print_section("E. PAY SETTINGS HISTORY")
    
    # Create a new employee for this test
    employee_data = {
        "first_name": "PaySettings",
        "last_name": "TestEmployee",
        "employment_type": "full_time"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees", json=employee_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees (for pay settings)", f"Status {resp.status_code}")
        return
    
    employee_id = resp.json()["employee_id"]
    log_pass(f"Created employee {employee_id} for pay settings test")
    
    # POST first pay setting
    pay_setting_1 = {
        "pay_basis": "hourly",
        "pay_frequency": "weekly",
        "base_hourly_rate": "30",
        "std_hours_per_week": "38",
        "effective_from": "2025-07-01"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees/{employee_id}/pay-settings", json=pay_setting_1)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees/{id}/pay-settings (first)", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass("POST /payroll/employees/{id}/pay-settings - first setting created")
    
    # POST second pay setting with later effective_from
    pay_setting_2 = {
        "pay_basis": "hourly",
        "pay_frequency": "weekly",
        "base_hourly_rate": "32",
        "std_hours_per_week": "38",
        "effective_from": "2026-07-01"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees/{employee_id}/pay-settings", json=pay_setting_2)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees/{id}/pay-settings (second)", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass("POST /payroll/employees/{id}/pay-settings - second setting created")
    
    # GET pay settings - should be sorted newest-first
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}/pay-settings")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees/{id}/pay-settings", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if "items" not in data:
        log_fail("GET /payroll/employees/{id}/pay-settings", "Missing 'items' in response")
        return
    
    items = data["items"]
    if len(items) < 2:
        log_fail("GET /payroll/employees/{id}/pay-settings", f"Expected 2 items, got {len(items)}")
        return
    
    # Verify sorted newest-first
    if items[0].get("effective_from") != "2026-07-01":
        log_fail("GET /payroll/employees/{id}/pay-settings", f"First item should be newest (2026-07-01), got: {items[0].get('effective_from')}")
        return
    
    # Verify older row has effective_to set
    older_row = items[1]
    if older_row.get("effective_to") != "2026-07-01":
        log_fail("GET /payroll/employees/{id}/pay-settings", f"Older row should have effective_to='2026-07-01', got: {older_row.get('effective_to')}")
        return
    
    # Verify newer row has effective_to=null
    newer_row = items[0]
    if newer_row.get("effective_to") is not None:
        log_fail("GET /payroll/employees/{id}/pay-settings", f"Newer row should have effective_to=null, got: {newer_row.get('effective_to')}")
        return
    
    log_pass("GET /payroll/employees/{id}/pay-settings - history correct (sorted, effective_to set)")

def test_super_profile():
    """F. Super profile"""
    print_section("F. SUPER PROFILE")
    
    # Create employee
    employee_data = {
        "first_name": "Super",
        "last_name": "TestEmployee",
        "employment_type": "full_time"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees", json=employee_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees (for super)", f"Status {resp.status_code}")
        return
    
    employee_id = resp.json()["employee_id"]
    
    # PUT super profile
    super_data = {
        "super_enabled": True,
        "fund_name": "AustralianSuper",
        "sg_rate": "0.12"
    }
    resp = session.put(f"{BASE_URL}/payroll/employees/{employee_id}/super", json=super_data)
    if resp.status_code != 200:
        log_fail(f"PUT /payroll/employees/{employee_id}/super", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass(f"PUT /payroll/employees/{employee_id}/super - saved successfully")
    
    # GET super profile
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}/super")
    if resp.status_code != 200:
        log_fail(f"GET /payroll/employees/{employee_id}/super", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if data.get("fund_name") != "AustralianSuper":
        log_fail(f"GET /payroll/employees/{employee_id}/super", f"fund_name mismatch: {data.get('fund_name')}")
        return
    if data.get("sg_rate") != "0.12":
        log_fail(f"GET /payroll/employees/{employee_id}/super", f"sg_rate mismatch: {data.get('sg_rate')}")
        return
    
    log_pass(f"GET /payroll/employees/{employee_id}/super - values correct")

def test_tax_settings():
    """G. Tax settings (OWNER-ONLY)"""
    print_section("G. TAX SETTINGS (OWNER-ONLY)")
    
    # Create employee
    employee_data = {
        "first_name": "Tax",
        "last_name": "TestEmployee",
        "employment_type": "full_time"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees", json=employee_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees (for tax)", f"Status {resp.status_code}")
        return
    
    employee_id = resp.json()["employee_id"]
    
    # GET tax settings (owner-only)
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}/tax")
    if resp.status_code != 200:
        log_fail(f"GET /payroll/employees/{employee_id}/tax", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass(f"GET /payroll/employees/{employee_id}/tax - 200 OK (owner access)")
    
    # PUT tax settings
    tax_data = {
        "tax_free_threshold": True,
        "manual_payg_override": "120"
    }
    resp = session.put(f"{BASE_URL}/payroll/employees/{employee_id}/tax", json=tax_data)
    if resp.status_code != 200:
        log_fail(f"PUT /payroll/employees/{employee_id}/tax", f"Status {resp.status_code}: {resp.text}")
        return
    
    data = resp.json()
    if data.get("tax_free_threshold") != True:
        log_fail(f"PUT /payroll/employees/{employee_id}/tax", f"tax_free_threshold mismatch: {data.get('tax_free_threshold')}")
        return
    if data.get("manual_payg_override") != "120":
        log_fail(f"PUT /payroll/employees/{employee_id}/tax", f"manual_payg_override mismatch: {data.get('manual_payg_override')}")
        return
    
    log_pass(f"PUT /payroll/employees/{employee_id}/tax - saved successfully")

def test_bank_details():
    """H. Bank details (OWNER-ONLY, encrypted, masked)"""
    print_section("H. BANK DETAILS (OWNER-ONLY, ENCRYPTED, MASKED)")
    
    # Create employee
    employee_data = {
        "first_name": "Bank",
        "last_name": "TestEmployee",
        "employment_type": "full_time"
    }
    resp = session.post(f"{BASE_URL}/payroll/employees", json=employee_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/employees (for bank)", f"Status {resp.status_code}")
        return
    
    employee_id = resp.json()["employee_id"]
    
    # PUT bank details
    bank_data = {
        "bsb": "062-000",
        "account_number": "12345678",
        "account_name": "Test"
    }
    resp = session.put(f"{BASE_URL}/payroll/employees/{employee_id}/bank", json=bank_data)
    if resp.status_code != 200:
        log_fail(f"PUT /payroll/employees/{employee_id}/bank", f"Status {resp.status_code}: {resp.text}")
        return
    log_pass(f"PUT /payroll/employees/{employee_id}/bank - saved successfully")
    
    # GET without reveal - should be masked
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}/bank")
    if resp.status_code != 200:
        log_fail(f"GET /payroll/employees/{employee_id}/bank", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if "bsb_masked" not in data or "account_number_masked" not in data:
        log_fail(f"GET /payroll/employees/{employee_id}/bank", "Missing masked fields")
        return
    
    if "bsb" in data or "account_number" in data:
        log_fail(f"GET /payroll/employees/{employee_id}/bank", "Raw values should not be present without reveal=true")
        return
    
    log_pass(f"GET /payroll/employees/{employee_id}/bank - masked correctly (no raw values)")
    
    # GET with reveal=true - should return raw values
    resp = session.get(f"{BASE_URL}/payroll/employees/{employee_id}/bank?reveal=true")
    if resp.status_code != 200:
        log_fail(f"GET /payroll/employees/{employee_id}/bank?reveal=true", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if data.get("bsb") != "062-000":
        log_fail(f"GET /payroll/employees/{employee_id}/bank?reveal=true", f"bsb mismatch: {data.get('bsb')}")
        return
    if data.get("account_number") != "12345678":
        log_fail(f"GET /payroll/employees/{employee_id}/bank?reveal=true", f"account_number mismatch: {data.get('account_number')}")
        return
    
    log_pass(f"GET /payroll/employees/{employee_id}/bank?reveal=true - raw values decrypted correctly")
    
    # Note: Audit log verification would require DB access, skipping for now
    log_warning("Audit log verification", "Skipped - requires direct DB access to verify 'reveal' action logged")

def test_pay_items():
    """I. Pay items CRUD"""
    print_section("I. PAY ITEMS CRUD")
    
    # Use timestamp to make code unique
    import time
    code_suffix = str(int(time.time() * 1000))[-6:]
    
    # POST - Create pay item
    pay_item_data = {
        "code": f"ORD{code_suffix}",
        "label": "Ordinary Hours",
        "kind": "earning",
        "calc_type": "hourly",
        "default_rate": "0",
        "taxable": True,
        "super_liable": True
    }
    resp = session.post(f"{BASE_URL}/payroll/pay-items", json=pay_item_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/pay-items", f"Status {resp.status_code}: {resp.text}")
        return
    
    pay_item = resp.json()
    log_pass(f"POST /payroll/pay-items - created {pay_item.get('pay_item_id')}")
    
    # POST duplicate code - should fail
    resp = session.post(f"{BASE_URL}/payroll/pay-items", json=pay_item_data)
    if resp.status_code != 400:
        log_fail("POST /payroll/pay-items (duplicate)", f"Expected 400, got {resp.status_code}")
        return
    log_pass("POST /payroll/pay-items (duplicate) - correctly rejected with 400")
    
    # GET list
    resp = session.get(f"{BASE_URL}/payroll/pay-items")
    if resp.status_code != 200:
        log_fail("GET /payroll/pay-items", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if "items" not in data:
        log_fail("GET /payroll/pay-items", "Missing 'items' in response")
        return
    
    found = any(item.get("code") == f"ORD{code_suffix}" for item in data["items"])
    if not found:
        log_fail("GET /payroll/pay-items", f"Pay item 'ORD{code_suffix}' not in list")
        return
    
    log_pass(f"GET /payroll/pay-items - contains 'ORD{code_suffix}'")

def test_leave_types():
    """J. Leave types"""
    print_section("J. LEAVE TYPES")
    
    # Use timestamp to make code unique
    import time
    code_suffix = str(int(time.time() * 1000))[-6:]
    
    # POST - Create leave type
    leave_type_data = {
        "code": f"annual{code_suffix}",
        "label": "Annual Leave",
        "accrual_hours_per_year": "152"
    }
    resp = session.post(f"{BASE_URL}/payroll/leave-types", json=leave_type_data)
    if resp.status_code != 200:
        log_fail("POST /payroll/leave-types", f"Status {resp.status_code}: {resp.text}")
        return
    
    leave_type = resp.json()
    log_pass(f"POST /payroll/leave-types - created {leave_type.get('leave_type_id')}")
    
    # GET list
    resp = session.get(f"{BASE_URL}/payroll/leave-types")
    if resp.status_code != 200:
        log_fail("GET /payroll/leave-types", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if "items" not in data:
        log_fail("GET /payroll/leave-types", "Missing 'items' in response")
        return
    
    found = any(item.get("code") == f"annual{code_suffix}" for item in data["items"])
    if not found:
        log_fail("GET /payroll/leave-types", f"Leave type 'annual{code_suffix}' not in list")
        return
    
    log_pass(f"GET /payroll/leave-types - contains 'annual{code_suffix}'")

def test_business_id_isolation():
    """K. Business-ID isolation"""
    print_section("K. BUSINESS-ID ISOLATION")
    
    # Get an employee to verify business_id is present
    resp = session.get(f"{BASE_URL}/payroll/employees")
    if resp.status_code != 200:
        log_fail("GET /payroll/employees (for business_id check)", f"Status {resp.status_code}")
        return
    
    data = resp.json()
    if not data.get("items"):
        log_warning("Business-ID isolation", "No employees to verify business_id field")
        return
    
    # Note: The API response should NOT contain _id (MongoDB internal ID)
    # but business_id should be present in the DB (we can't verify without DB access)
    first_employee = data["items"][0]
    if "_id" in first_employee:
        log_fail("Business-ID isolation", "Response contains MongoDB _id field (should be removed)")
        return
    
    log_pass("Business-ID isolation - _id field correctly removed from response")
    log_warning("Business-ID isolation", "Full verification requires DB access to confirm business_id field exists")

def test_regression_smoke():
    """L. Regression smoke tests"""
    print_section("L. REGRESSION SMOKE TESTS")
    
    endpoints = [
        ("GET /api/", {}),
        ("GET /api/auth/me", {}),
        ("GET /api/auth/config", {}),
        ("GET /api/dashboard", {"fy": "FY2026-27", "period": "fy"}),
        ("GET /api/transactions", {"fy": "FY2026-27"}),
        ("GET /api/inventory/purchases", {}),
        ("GET /api/documents", {}),
        ("GET /api/reminders", {"fy": "FY2026-27"}),
        ("GET /api/reports", {}),
    ]
    
    for method_path, params in endpoints:
        method, path = method_path.split(" ", 1)
        url = f"{BASE_URL}{path.replace('/api', '')}"
        
        if method == "GET":
            resp = session.get(url, params=params)
        else:
            resp = session.request(method, url, params=params)
        
        if resp.status_code != 200:
            log_fail(f"Regression: {method_path}", f"Status {resp.status_code}: {resp.text[:200]}")
        else:
            log_pass(f"Regression: {method_path}")
    
    # Test document upload/download
    print("\nTesting document upload/download...")
    
    # Upload
    files = {"file": ("test.txt", b"Test content for regression", "text/plain")}
    resp = session.post(f"{BASE_URL}/documents/upload", files=files)
    if resp.status_code != 200:
        log_fail("Regression: POST /documents/upload", f"Status {resp.status_code}")
    else:
        doc_id = resp.json().get("document_id")
        log_pass("Regression: POST /documents/upload")
        
        # Download
        resp = session.get(f"{BASE_URL}/documents/{doc_id}/download")
        if resp.status_code != 200:
            log_fail("Regression: GET /documents/{id}/download", f"Status {resp.status_code}")
        elif resp.content != b"Test content for regression":
            log_fail("Regression: GET /documents/{id}/download", "Downloaded bytes don't match")
        else:
            log_pass("Regression: GET /documents/{id}/download - bytes match")
    
    # Test accountant export
    print("\nTesting accountant export...")
    resp = session.post(f"{BASE_URL}/export/accountant", json={
        "fy": "FY2026-27",
        "reports": ["pnl", "balance_sheet"],
        "format": "zip",
        "include_receipts": True
    })
    if resp.status_code != 200:
        log_fail("Regression: POST /export/accountant", f"Status {resp.status_code}")
    elif resp.headers.get("content-type") != "application/zip":
        log_fail("Regression: POST /export/accountant", f"Wrong content-type: {resp.headers.get('content-type')}")
    else:
        log_pass("Regression: POST /export/accountant - returns application/zip")

def print_summary():
    """Print test summary"""
    print_section("TEST SUMMARY")
    
    total = len(results["passed"]) + len(results["failed"])
    print(f"Total tests: {total}")
    print(f"✅ Passed: {len(results['passed'])}")
    print(f"❌ Failed: {len(results['failed'])}")
    print(f"⚠️  Warnings: {len(results['warnings'])}")
    
    if results["failed"]:
        print("\n" + "="*80)
        print("FAILED TESTS:")
        print("="*80)
        for fail in results["failed"]:
            print(f"\n❌ {fail['test']}")
            print(f"   {fail['reason']}")
    
    if results["warnings"]:
        print("\n" + "="*80)
        print("WARNINGS:")
        print("="*80)
        for warn in results["warnings"]:
            print(f"\n⚠️  {warn['test']}")
            print(f"   {warn['message']}")
    
    print("\n" + "="*80)
    if results["failed"]:
        print("❌ SOME TESTS FAILED")
        return 1
    else:
        print("✅ ALL TESTS PASSED")
        return 0

def main():
    """Run all tests"""
    try:
        # Login
        user_data = login()
        
        # Run payroll tests
        test_payroll_status()
        test_employer_profile()
        test_fy_dropdown()
        test_employees_crud()
        test_pay_settings_history()
        test_super_profile()
        test_tax_settings()
        test_bank_details()
        test_pay_items()
        test_leave_types()
        
        # Business-ID isolation
        test_business_id_isolation()
        
        # Regression smoke
        test_regression_smoke()
        
        # Print summary
        return print_summary()
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
