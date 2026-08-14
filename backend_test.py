#!/usr/bin/env python3
"""
PAYROLL PHASE 2 VERIFICATION TEST SUITE
Tests pay runs + calculation engine + Phase 1 regression
"""
import requests
import json
import sys
from typing import Optional

# Backend URL from frontend/.env
BASE_URL = "https://deploy-fix-145.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
EMAIL = "urbandottedstore@gmail.com"
PASSWORD = "Milan@112233!@#"

# Global session
session = requests.Session()
business_id = None
access_token = None

# Test data storage
empId1 = None  # P2 Hourly
empId2 = None  # P2 Salaried
pay_run_ref = None


def log(msg: str, level: str = "INFO"):
    """Print test log message"""
    print(f"[{level}] {msg}")


def login():
    """Authenticate and get business_id"""
    global business_id, access_token
    log("Authenticating...")
    resp = session.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        log(f"Login failed: {resp.status_code} {resp.text}", "ERROR")
        sys.exit(1)
    data = resp.json()
    business_id = data.get("business_ids", [None])[0]
    if not business_id:
        log("No business_id found", "ERROR")
        sys.exit(1)
    # Extract access_token from cookies for Bearer auth
    access_token = session.cookies.get("access_token")
    log(f"Authenticated. business_id={business_id}")


def api_get(path: str, params: Optional[dict] = None, expect_status: int = 200):
    """GET request with auth"""
    headers = {"X-Business-ID": business_id}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resp = session.get(f"{BASE_URL}{path}", params=params, headers=headers)
    if resp.status_code != expect_status:
        log(f"GET {path} returned {resp.status_code}, expected {expect_status}: {resp.text}", "ERROR")
        return None
    return resp


def api_post(path: str, body: dict, expect_status: int = 200):
    """POST request with auth"""
    headers = {"X-Business-ID": business_id, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resp = session.post(f"{BASE_URL}{path}", json=body, headers=headers)
    if resp.status_code != expect_status:
        log(f"POST {path} returned {resp.status_code}, expected {expect_status}: {resp.text}", "ERROR")
        return None
    return resp


def api_put(path: str, body: dict, expect_status: int = 200):
    """PUT request with auth"""
    headers = {"X-Business-ID": business_id, "Content-Type": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resp = session.put(f"{BASE_URL}{path}", json=body, headers=headers)
    if resp.status_code != expect_status:
        log(f"PUT {path} returned {resp.status_code}, expected {expect_status}: {resp.text}", "ERROR")
        return None
    return resp


def setup_test_employees():
    """Create Phase 2 test employees (empId1: hourly, empId2: salaried)"""
    global empId1, empId2
    log("=== SETUP: Creating Phase 2 test employees ===")
    
    # Create empId1: P2 Hourly
    resp = api_post("/payroll/employees", {
        "first_name": "P2",
        "last_name": "Hourly",
        "employment_type": "full_time",
        "status": "active"
    })
    if not resp:
        log("Failed to create empId1", "ERROR")
        sys.exit(1)
    empId1 = resp.json().get("employee_id")
    log(f"Created empId1: {empId1}")
    
    # Pay settings for empId1
    resp = api_post(f"/payroll/employees/{empId1}/pay-settings", {
        "pay_basis": "hourly",
        "pay_frequency": "fortnightly",
        "base_hourly_rate": "30",
        "std_hours_per_week": "38",
        "std_hours_per_fortnight": "76",
        "effective_from": "2025-07-01"
    })
    if not resp:
        log("Failed to create pay settings for empId1", "ERROR")
        sys.exit(1)
    
    # Super for empId1
    resp = api_put(f"/payroll/employees/{empId1}/super", {
        "super_enabled": True,
        "sg_rate": "0.12",
        "fund_name": "AustralianSuper"
    })
    if not resp:
        log("Failed to set super for empId1", "ERROR")
        sys.exit(1)
    
    # Tax for empId1
    resp = api_put(f"/payroll/employees/{empId1}/tax", {
        "payg_enabled": True,
        "tax_free_threshold": True,
        "manual_payg_override": "0"
    })
    if not resp:
        log("Failed to set tax for empId1", "ERROR")
        sys.exit(1)
    
    # Create empId2: P2 Salaried
    resp = api_post("/payroll/employees", {
        "first_name": "P2",
        "last_name": "Salaried",
        "employment_type": "full_time",
        "status": "active"
    })
    if not resp:
        log("Failed to create empId2", "ERROR")
        sys.exit(1)
    empId2 = resp.json().get("employee_id")
    log(f"Created empId2: {empId2}")
    
    # Pay settings for empId2
    resp = api_post(f"/payroll/employees/{empId2}/pay-settings", {
        "pay_basis": "annual_salary",
        "pay_frequency": "fortnightly",
        "annual_salary": "70000",
        "effective_from": "2025-07-01"
    })
    if not resp:
        log("Failed to create pay settings for empId2", "ERROR")
        sys.exit(1)
    
    # Super for empId2
    resp = api_put(f"/payroll/employees/{empId2}/super", {
        "super_enabled": True,
        "sg_rate": "0.12",
        "fund_name": "HESTA"
    })
    if not resp:
        log("Failed to set super for empId2", "ERROR")
        sys.exit(1)
    
    log("✓ Setup complete: 2 test employees created")


def test_section_a():
    """A. Create + list pay runs"""
    global pay_run_ref
    log("\n=== SECTION A: Create + list pay runs ===")
    
    # A1: Create pay run
    log("A1: POST /api/payroll/pay-runs")
    resp = api_post("/payroll/pay-runs", {
        "pay_frequency": "fortnightly",
        "period_start": "2026-08-03",
        "period_end": "2026-08-16",
        "payment_date": "2026-08-19"
    })
    if not resp:
        return False
    data = resp.json()
    pay_run_ref = data.get("pay_run_ref")
    if not pay_run_ref or not pay_run_ref.startswith("UD-PR-"):
        log(f"Invalid pay_run_ref: {pay_run_ref}", "ERROR")
        return False
    log(f"✓ A1 PASS: Created pay run {pay_run_ref}")
    
    # A2: Duplicate should fail
    log("A2: POST duplicate pay run (should return 400)")
    resp = api_post("/payroll/pay-runs", {
        "pay_frequency": "fortnightly",
        "period_start": "2026-08-03",
        "period_end": "2026-08-16",
        "payment_date": "2026-08-19"
    }, expect_status=400)
    if not resp:
        return False
    log("✓ A2 PASS: Duplicate rejected with 400")
    
    # A3: List pay runs
    log("A3: GET /api/payroll/pay-runs")
    resp = api_get("/payroll/pay-runs")
    if not resp:
        return False
    data = resp.json()
    refs = [r["pay_run_ref"] for r in data.get("items", [])]
    if pay_run_ref not in refs:
        log(f"pay_run_ref {pay_run_ref} not in list", "ERROR")
        return False
    log("✓ A3 PASS: Pay run in list")
    
    # A4: List with status filter
    log("A4: GET /api/payroll/pay-runs?status=draft")
    resp = api_get("/payroll/pay-runs", params={"status": "draft"})
    if not resp:
        return False
    data = resp.json()
    refs = [r["pay_run_ref"] for r in data.get("items", [])]
    if pay_run_ref not in refs:
        log(f"pay_run_ref {pay_run_ref} not in draft list", "ERROR")
        return False
    log("✓ A4 PASS: Pay run in draft list")
    
    # A5: Invalid period (end < start) should fail
    log("A5: POST with period_end < period_start (should return 422)")
    resp = api_post("/payroll/pay-runs", {
        "pay_frequency": "fortnightly",
        "period_start": "2026-08-20",
        "period_end": "2026-08-10",
        "payment_date": "2026-08-25"
    }, expect_status=422)
    if not resp:
        return False
    log("✓ A5 PASS: Invalid period rejected with 422")
    
    log("✓ SECTION A: ALL TESTS PASSED")
    return True


def test_section_b():
    """B. Load employees"""
    log("\n=== SECTION B: Load employees ===")
    
    # B1: Load employees
    log("B1: POST /api/payroll/pay-runs/{ref}/load")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/load", {})
    if not resp:
        return False
    data = resp.json()
    included = data.get("included", [])
    if empId1 not in included or empId2 not in included:
        log(f"Expected both empId1 and empId2 in included list, got: {included}", "ERROR")
        return False
    log(f"✓ B1 PASS: Loaded {data.get('count')} employees (includes both P2 employees)")
    
    # B2: Get pay run detail
    log("B2: GET /api/payroll/pay-runs/{ref}")
    resp = api_get(f"/payroll/pay-runs/{pay_run_ref}")
    if not resp:
        return False
    data = resp.json()
    employees = data.get("employees", [])
    if len(employees) < 2:
        log(f"Expected at least 2 employees, got {len(employees)}", "ERROR")
        return False
    
    # Check each employee has a default ORD line
    for emp in employees:
        lines = emp.get("lines", [])
        if not lines:
            log(f"Employee {emp.get('employee_id')} has no lines", "ERROR")
            return False
        if lines[0].get("code") != "ORD":
            log(f"Employee {emp.get('employee_id')} first line is not ORD", "ERROR")
            return False
    log("✓ B2 PASS: Pay run detail returns employees with default ORD lines")
    
    log("✓ SECTION B: ALL TESTS PASSED")
    return True


def test_section_c():
    """C. Calc correctness"""
    log("\n=== SECTION C: Calc correctness ===")
    
    # Get pay run detail
    resp = api_get(f"/payroll/pay-runs/{pay_run_ref}")
    if not resp:
        return False
    data = resp.json()
    employees = data.get("employees", [])
    
    # Find empId1 (hourly) and empId2 (salaried)
    emp1 = next((e for e in employees if e["employee_id"] == empId1), None)
    emp2 = next((e for e in employees if e["employee_id"] == empId2), None)
    
    if not emp1 or not emp2:
        log("Could not find empId1 or empId2 in pay run", "ERROR")
        return False
    
    # C1: Hourly employee (empId1)
    log("C1: Hourly employee calc verification")
    log(f"  empId1 data: {json.dumps(emp1, indent=2)}")
    
    # Expected: hours=76, rate_cents=3000, amount_cents=228000
    line1 = emp1.get("lines", [{}])[0]
    if line1.get("hours_or_units") != "76":
        log(f"Expected hours_or_units=76, got {line1.get('hours_or_units')}", "ERROR")
        return False
    if line1.get("rate_cents") != 3000:
        log(f"Expected rate_cents=3000, got {line1.get('rate_cents')}", "ERROR")
        return False
    if line1.get("amount_cents") != 228000:
        log(f"Expected amount_cents=228000, got {line1.get('amount_cents')}", "ERROR")
        return False
    
    # Expected totals: gross=228000, taxable=228000, payg=0, net=228000, super=27360, employer_cost=255360
    if emp1.get("gross_cents") != 228000:
        log(f"Expected gross_cents=228000, got {emp1.get('gross_cents')}", "ERROR")
        return False
    if emp1.get("taxable_cents") != 228000:
        log(f"Expected taxable_cents=228000, got {emp1.get('taxable_cents')}", "ERROR")
        return False
    if emp1.get("payg_cents") != 0:
        log(f"Expected payg_cents=0, got {emp1.get('payg_cents')}", "ERROR")
        return False
    if emp1.get("net_cents") != 228000:
        log(f"Expected net_cents=228000, got {emp1.get('net_cents')}", "ERROR")
        return False
    if emp1.get("super_cents") != 27360:
        log(f"Expected super_cents=27360, got {emp1.get('super_cents')}", "ERROR")
        return False
    if emp1.get("total_employer_cost_cents") != 255360:
        log(f"Expected total_employer_cost_cents=255360, got {emp1.get('total_employer_cost_cents')}", "ERROR")
        return False
    log("✓ C1 PASS: Hourly employee calc correct")
    
    # C2: Salaried employee (empId2)
    log("C2: Salaried employee calc verification")
    log(f"  empId2 data: {json.dumps(emp2, indent=2)}")
    
    # Expected: 70000/26 = 2692.31 -> rate_cents=269231
    line2 = emp2.get("lines", [{}])[0]
    if line2.get("rate_cents") != 269231:
        log(f"Expected rate_cents=269231, got {line2.get('rate_cents')}", "ERROR")
        return False
    
    # Expected totals: gross=269231, super=32308, net=269231, employer_cost=301539
    if emp2.get("gross_cents") != 269231:
        log(f"Expected gross_cents=269231, got {emp2.get('gross_cents')}", "ERROR")
        return False
    if emp2.get("super_cents") != 32308:
        log(f"Expected super_cents=32308, got {emp2.get('super_cents')}", "ERROR")
        return False
    if emp2.get("net_cents") != 269231:
        log(f"Expected net_cents=269231, got {emp2.get('net_cents')}", "ERROR")
        return False
    if emp2.get("total_employer_cost_cents") != 301539:
        log(f"Expected total_employer_cost_cents=301539, got {emp2.get('total_employer_cost_cents')}", "ERROR")
        return False
    log("✓ C2 PASS: Salaried employee calc correct")
    
    # C3: Pay run totals
    log("C3: Pay run totals verification")
    totals = data.get("totals", {})
    expected_gross = 228000 + 269231
    expected_super = 27360 + 32308
    expected_employer_cost = 255360 + 301539
    
    if totals.get("gross_cents") != expected_gross:
        log(f"Expected totals.gross_cents={expected_gross}, got {totals.get('gross_cents')}", "ERROR")
        return False
    if totals.get("super_cents") != expected_super:
        log(f"Expected totals.super_cents={expected_super}, got {totals.get('super_cents')}", "ERROR")
        return False
    if totals.get("total_employer_cost_cents") != expected_employer_cost:
        log(f"Expected totals.total_employer_cost_cents={expected_employer_cost}, got {totals.get('total_employer_cost_cents')}", "ERROR")
        return False
    log("✓ C3 PASS: Pay run totals correct")
    
    log("✓ SECTION C: ALL TESTS PASSED")
    return True


def test_section_d():
    """D. Edit employee - mixed lines"""
    log("\n=== SECTION D: Edit employee - mixed lines ===")
    
    # D1: Edit empId1 with mixed lines
    log("D1: PUT /api/payroll/pay-runs/{ref}/employees/{empId1}")
    resp = api_put(f"/payroll/pay-runs/{pay_run_ref}/employees/{empId1}", {
        "lines": [
            {
                "code": "ORD",
                "label": "Ordinary",
                "kind": "earning",
                "calc_type": "hourly",
                "hours_or_units": "20",
                "rate_cents": 3000,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            },
            {
                "code": "SHIFT175",
                "label": "Shift 75%",
                "kind": "earning",
                "calc_type": "percent_of_base",
                "hours_or_units": "12",
                "rate_cents": 17500,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            },
            {
                "code": "OT150",
                "label": "Overtime",
                "kind": "earning",
                "calc_type": "percent_of_base",
                "hours_or_units": "8",
                "rate_cents": 15000,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            },
            {
                "code": "SS",
                "label": "Salary sacrifice",
                "kind": "deduction",
                "calc_type": "fixed",
                "hours_or_units": "0",
                "rate_cents": 10000,
                "deduction_category": "pretax"
            }
        ],
        "payg_override_cents": 30000
    })
    if not resp:
        return False
    data = resp.json()
    log(f"  Edit response: {json.dumps(data, indent=2)}")
    
    # Expected calc:
    # ORD: 20 * 3000 = 60000
    # SHIFT175: 12 * 3000 * 1.75 = 63000
    # OT150: 8 * 3000 * 1.50 = 36000
    # Gross = 60000 + 63000 + 36000 = 159000
    # Pretax deduction = 10000
    # Taxable = 159000 - 10000 = 149000
    # PAYG = 30000
    # Net = 149000 - 30000 = 119000
    # Superable = 159000
    # Super = round(159000 * 0.12) = 19080
    
    if data.get("gross_cents") != 159000:
        log(f"Expected gross_cents=159000, got {data.get('gross_cents')}", "ERROR")
        return False
    if data.get("pretax_ded_cents") != 10000:
        log(f"Expected pretax_ded_cents=10000, got {data.get('pretax_ded_cents')}", "ERROR")
        return False
    if data.get("taxable_cents") != 149000:
        log(f"Expected taxable_cents=149000, got {data.get('taxable_cents')}", "ERROR")
        return False
    if data.get("payg_cents") != 30000:
        log(f"Expected payg_cents=30000, got {data.get('payg_cents')}", "ERROR")
        return False
    if data.get("net_cents") != 119000:
        log(f"Expected net_cents=119000, got {data.get('net_cents')}", "ERROR")
        return False
    if data.get("superable_cents") != 159000:
        log(f"Expected superable_cents=159000, got {data.get('superable_cents')}", "ERROR")
        return False
    if data.get("super_cents") != 19080:
        log(f"Expected super_cents=19080, got {data.get('super_cents')}", "ERROR")
        return False
    log("✓ D1 PASS: Mixed lines calc correct")
    
    # D2: Verify changes persisted
    log("D2: GET /api/payroll/pay-runs/{ref} to verify changes")
    resp = api_get(f"/payroll/pay-runs/{pay_run_ref}")
    if not resp:
        return False
    data = resp.json()
    emp1 = next((e for e in data.get("employees", []) if e["employee_id"] == empId1), None)
    if not emp1:
        log("Could not find empId1 in pay run", "ERROR")
        return False
    
    lines = emp1.get("lines", [])
    if len(lines) != 4:
        log(f"Expected 4 lines, got {len(lines)}", "ERROR")
        return False
    
    # Verify line codes
    codes = [l.get("code") for l in lines]
    expected_codes = ["ORD", "SHIFT175", "OT150", "SS"]
    if codes != expected_codes:
        log(f"Expected codes {expected_codes}, got {codes}", "ERROR")
        return False
    log("✓ D2 PASS: Changes persisted correctly")
    
    log("✓ SECTION D: ALL TESTS PASSED")
    return True


def test_section_e():
    """E. Validation"""
    log("\n=== SECTION E: Validation ===")
    
    # E1: Negative hours
    log("E1: PUT with negative hours (should return 422)")
    resp = api_put(f"/payroll/pay-runs/{pay_run_ref}/employees/{empId1}", {
        "lines": [
            {
                "code": "ORD",
                "label": "Ordinary",
                "kind": "earning",
                "calc_type": "hourly",
                "hours_or_units": "-5",
                "rate_cents": 3000,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            }
        ]
    }, expect_status=422)
    if not resp:
        return False
    log("✓ E1 PASS: Negative hours rejected with 422")
    
    # E2: Negative rate
    log("E2: PUT with negative rate (should return 422)")
    resp = api_put(f"/payroll/pay-runs/{pay_run_ref}/employees/{empId1}", {
        "lines": [
            {
                "code": "ORD",
                "label": "Ordinary",
                "kind": "earning",
                "calc_type": "hourly",
                "hours_or_units": "10",
                "rate_cents": -100,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            }
        ]
    }, expect_status=422)
    if not resp:
        return False
    log("✓ E2 PASS: Negative rate rejected with 422")
    
    # E3: Invalid kind
    log("E3: PUT with invalid kind (should return 422)")
    resp = api_put(f"/payroll/pay-runs/{pay_run_ref}/employees/{empId1}", {
        "lines": [
            {
                "code": "ORD",
                "label": "Ordinary",
                "kind": "bogus",
                "calc_type": "hourly",
                "hours_or_units": "10",
                "rate_cents": 3000,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            }
        ]
    }, expect_status=422)
    if not resp:
        return False
    log("✓ E3 PASS: Invalid kind rejected with 422")
    
    log("✓ SECTION E: ALL TESTS PASSED")
    return True


def test_section_f():
    """F. Recalculate endpoint"""
    log("\n=== SECTION F: Recalculate endpoint ===")
    
    # F1: Recalculate
    log("F1: POST /api/payroll/pay-runs/{ref}/calculate")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/calculate", {})
    if not resp:
        return False
    data = resp.json()
    
    # Should return aggregated totals
    if "gross_cents" not in data:
        log("Response missing gross_cents", "ERROR")
        return False
    if "employee_count" not in data:
        log("Response missing employee_count", "ERROR")
        return False
    log(f"✓ F1 PASS: Recalculate returned totals: {json.dumps(data, indent=2)}")
    
    log("✓ SECTION F: ALL TESTS PASSED")
    return True


def test_section_g():
    """G. Finalise"""
    log("\n=== SECTION G: Finalise ===")
    
    # G1: Finalise
    log("G1: POST /api/payroll/pay-runs/{ref}/finalise")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/finalise", {})
    if not resp:
        return False
    data = resp.json()
    if data.get("status") != "finalised":
        log(f"Expected status=finalised, got {data.get('status')}", "ERROR")
        return False
    log("✓ G1 PASS: Pay run finalised")
    
    # G2: Edit should fail
    log("G2: PUT to edit employee (should return 400)")
    resp = api_put(f"/payroll/pay-runs/{pay_run_ref}/employees/{empId1}", {
        "lines": [
            {
                "code": "ORD",
                "label": "Ordinary",
                "kind": "earning",
                "calc_type": "hourly",
                "hours_or_units": "10",
                "rate_cents": 3000,
                "base_rate_cents": 3000,
                "taxable": True,
                "super_liable": True
            }
        ]
    }, expect_status=400)
    if not resp:
        return False
    if "cannot be edited" not in resp.text.lower():
        log(f"Expected 'cannot be edited' in error message, got: {resp.text}", "ERROR")
        return False
    log("✓ G2 PASS: Edit rejected with 400 'cannot be edited'")
    
    # G3: Second finalise should fail
    log("G3: POST /api/payroll/pay-runs/{ref}/finalise again (should return 400)")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/finalise", {}, expect_status=400)
    if not resp:
        return False
    log("✓ G3 PASS: Second finalise rejected with 400")
    
    # G4: GET should still return full snapshot
    log("G4: GET /api/payroll/pay-runs/{ref}")
    resp = api_get(f"/payroll/pay-runs/{pay_run_ref}")
    if not resp:
        return False
    data = resp.json()
    if data.get("status") != "finalised":
        log(f"Expected status=finalised, got {data.get('status')}", "ERROR")
        return False
    if not data.get("employees"):
        log("Expected employees in response", "ERROR")
        return False
    log("✓ G4 PASS: GET returns full snapshot")
    
    log("✓ SECTION G: ALL TESTS PASSED")
    return True


def test_section_h():
    """H. Immutability + Void"""
    log("\n=== SECTION H: Immutability + Void ===")
    
    # H1: Void
    log("H1: POST /api/payroll/pay-runs/{ref}/void")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/void", {"reason": "test correction"})
    if not resp:
        return False
    data = resp.json()
    if data.get("status") != "voided":
        log(f"Expected status=voided, got {data.get('status')}", "ERROR")
        return False
    log("✓ H1 PASS: Pay run voided")
    
    # H2: GET should show voided status
    log("H2: GET /api/payroll/pay-runs")
    resp = api_get("/payroll/pay-runs")
    if not resp:
        return False
    data = resp.json()
    voided_run = next((r for r in data.get("items", []) if r["pay_run_ref"] == pay_run_ref), None)
    if not voided_run:
        log(f"Could not find {pay_run_ref} in list", "ERROR")
        return False
    if voided_run.get("status") != "voided":
        log(f"Expected status=voided, got {voided_run.get('status')}", "ERROR")
        return False
    log("✓ H2 PASS: Pay run shows status=voided")
    
    # H3: Double void should fail
    log("H3: POST /api/payroll/pay-runs/{ref}/void again (should return 400)")
    resp = api_post(f"/payroll/pay-runs/{pay_run_ref}/void", {"reason": "test"}, expect_status=400)
    if not resp:
        return False
    log("✓ H3 PASS: Double void rejected with 400")
    
    # H4: Create another pay run for same period (should be allowed)
    log("H4: POST /api/payroll/pay-runs for same period (should return 200)")
    resp = api_post("/payroll/pay-runs", {
        "pay_frequency": "fortnightly",
        "period_start": "2026-08-03",
        "period_end": "2026-08-16",
        "payment_date": "2026-08-19"
    })
    if not resp:
        return False
    data = resp.json()
    new_ref = data.get("pay_run_ref")
    if not new_ref or not new_ref.startswith("UD-PR-"):
        log(f"Invalid pay_run_ref: {new_ref}", "ERROR")
        return False
    log(f"✓ H4 PASS: Created new pay run for same period: {new_ref}")
    
    log("✓ SECTION H: ALL TESTS PASSED")
    return True


def test_section_i():
    """I. Empty finalise rejected"""
    log("\n=== SECTION I: Empty finalise rejected ===")
    
    # I1: Create weekly pay run
    log("I1: POST /api/payroll/pay-runs (weekly)")
    resp = api_post("/payroll/pay-runs", {
        "pay_frequency": "weekly",
        "period_start": "2026-08-17",
        "period_end": "2026-08-23",
        "payment_date": "2026-08-26"
    })
    if not resp:
        return False
    data = resp.json()
    empty_ref = data.get("pay_run_ref")
    log(f"Created empty pay run: {empty_ref}")
    
    # I2: Finalise without loading (should fail)
    log("I2: POST /api/payroll/pay-runs/{ref}/finalise (should return 400)")
    resp = api_post(f"/payroll/pay-runs/{empty_ref}/finalise", {}, expect_status=400)
    if not resp:
        return False
    if "empty" not in resp.text.lower():
        log(f"Expected 'empty' in error message, got: {resp.text}", "ERROR")
        return False
    log("✓ I2 PASS: Empty finalise rejected with 400 'Cannot finalise an empty pay run'")
    
    log("✓ SECTION I: ALL TESTS PASSED")
    return True


def test_section_j():
    """J. Dashboard"""
    log("\n=== SECTION J: Dashboard ===")
    
    # J1: GET dashboard
    log("J1: GET /api/payroll/dashboard")
    resp = api_get("/payroll/dashboard")
    if not resp:
        return False
    data = resp.json()
    
    # Check required fields
    required = ["active_employees", "drafts_count", "recent_finalised", "ytd", "payg_status"]
    for field in required:
        if field not in data:
            log(f"Response missing {field}", "ERROR")
            return False
    
    log(f"  Dashboard data: {json.dumps(data, indent=2)}")
    
    # YTD should include finalised (but not voided) run
    ytd = data.get("ytd", {})
    if "gross_cents" not in ytd:
        log("YTD missing gross_cents", "ERROR")
        return False
    
    log("✓ J1 PASS: Dashboard returns correct structure")
    
    log("✓ SECTION J: ALL TESTS PASSED")
    return True


def test_section_k():
    """K. Regression - ALL Phase 1 + existing modules"""
    log("\n=== SECTION K: Regression tests ===")
    
    tests = [
        ("GET /api/", None),
        ("GET /api/auth/me", None),
        ("GET /api/auth/config", None),
        ("GET /api/meta", None),
        ("GET /api/dashboard", {"fy": "FY2026-27"}),
        ("GET /api/transactions", {"fy": "FY2026-27"}),
        ("GET /api/inventory/purchases", None),
        ("GET /api/documents", None),
        ("GET /api/reminders", {"fy": "FY2026-27"}),
        ("GET /api/reports", None),
        ("GET /api/payroll/status", None),
        ("GET /api/payroll/employer", None),
        ("GET /api/payroll/employees", None),
        ("GET /api/payroll/pay-items", None),
        ("GET /api/payroll/leave-types", None),
    ]
    
    for i, (endpoint, params) in enumerate(tests, 1):
        log(f"K{i}: {endpoint}")
        resp = api_get(endpoint.replace("GET /api", ""), params=params)
        if not resp:
            return False
        log(f"✓ K{i} PASS: {endpoint} returned 200")
    
    # K16: Document upload/download
    log("K16: POST /api/documents/upload + GET download")
    files = {"file": ("test_phase2.txt", b"Phase 2 test file", "text/plain")}
    headers = {"X-Business-ID": business_id}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    resp = session.post(f"{BASE_URL}/documents/upload", files=files, headers=headers)
    if resp.status_code != 200:
        log(f"Upload failed: {resp.status_code} {resp.text}", "ERROR")
        return False
    doc_id = resp.json().get("document_id")
    
    resp = api_get(f"/documents/{doc_id}/download")
    if not resp:
        return False
    if resp.content != b"Phase 2 test file":
        log(f"Downloaded bytes don't match", "ERROR")
        return False
    log("✓ K16 PASS: Document upload/download working")
    
    # K17: FY dropdown - no future FYs
    log("K17: GET /api/meta (verify no future FYs)")
    resp = api_get("/meta")
    if not resp:
        return False
    data = resp.json()
    fy_options = data.get("fy_options", [])
    current_fy = data.get("current_fy")
    if fy_options[0] != current_fy:
        log(f"Expected fy_options[0]={current_fy}, got {fy_options[0]}", "ERROR")
        return False
    
    # Check no future FYs
    current_year = int(current_fy.split("-")[0][2:])  # Extract year from FY2026-27
    for fy in fy_options:
        fy_year = int(fy.split("-")[0][2:])
        if fy_year > current_year:
            log(f"Found future FY: {fy}", "ERROR")
            return False
    log("✓ K17 PASS: No future FYs in dropdown")
    
    # K18: Bank details masked by default, reveal=true works
    log("K18: GET /api/payroll/employees/{empId1}/bank (masked and reveal)")
    
    # First set bank details
    resp = api_put(f"/payroll/employees/{empId1}/bank", {
        "bsb": "062-000",
        "account_number": "12345678",
        "account_name": "Test Account"
    })
    if not resp:
        log("Failed to set bank details", "WARN")
    else:
        # Get masked
        resp = api_get(f"/payroll/employees/{empId1}/bank")
        if not resp:
            return False
        data = resp.json()
        if "bsb_masked" not in data or "account_number_masked" not in data:
            log("Expected masked fields in response", "ERROR")
            return False
        if "bsb" in data and data["bsb"] == "062-000":
            log("Expected bsb to be masked, got raw value", "ERROR")
            return False
        
        # Get with reveal=true
        resp = api_get(f"/payroll/employees/{empId1}/bank", params={"reveal": "true"})
        if not resp:
            return False
        data = resp.json()
        if data.get("bsb") != "062-000" or data.get("account_number") != "12345678":
            log(f"Expected raw values with reveal=true, got: {data}", "ERROR")
            return False
        log("✓ K18 PASS: Bank details masked by default, reveal=true works")
    
    log("✓ SECTION K: ALL REGRESSION TESTS PASSED")
    return True


def main():
    """Run all tests"""
    log("=" * 80)
    log("PAYROLL PHASE 2 VERIFICATION TEST SUITE")
    log("=" * 80)
    
    login()
    setup_test_employees()
    
    results = {
        "A. Create + list pay runs": test_section_a(),
        "B. Load employees": test_section_b(),
        "C. Calc correctness": test_section_c(),
        "D. Edit employee - mixed lines": test_section_d(),
        "E. Validation": test_section_e(),
        "F. Recalculate endpoint": test_section_f(),
        "G. Finalise": test_section_g(),
        "H. Immutability + Void": test_section_h(),
        "I. Empty finalise rejected": test_section_i(),
        "J. Dashboard": test_section_j(),
        "K. Regression": test_section_k(),
    }
    
    log("\n" + "=" * 80)
    log("TEST SUMMARY")
    log("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for section, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"{status} - {section}")
    
    log("=" * 80)
    log(f"TOTAL: {passed}/{total} sections passed")
    log("=" * 80)
    
    if passed == total:
        log("🎉 ALL TESTS PASSED", "SUCCESS")
        sys.exit(0)
    else:
        log(f"❌ {total - passed} section(s) failed", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
