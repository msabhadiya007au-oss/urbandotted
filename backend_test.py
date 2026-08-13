#!/usr/bin/env python3
"""
Deployment-readiness smoke test for Urban Dotted Expense Book backend.
Tests all critical endpoints to verify the deployment refactor hasn't broken existing features.
"""
import requests
import json
import io
import sys
from datetime import datetime

# Test configuration
BASE_URL = "http://localhost:8001"
TEST_EMAIL = "admin@urbandotted.com.au"
TEST_PASSWORD = "UrbanDotted!2026"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BLUE = '\033[94m'

class TestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.business_id = None
        self.passed = 0
        self.failed = 0
        self.errors = []
        
    def log(self, message, status="INFO"):
        colors = {"PASS": GREEN, "FAIL": RED, "INFO": BLUE, "WARN": YELLOW}
        color = colors.get(status, RESET)
        print(f"{color}[{status}]{RESET} {message}")
        
    def test(self, name, func):
        """Run a test function and track results"""
        try:
            self.log(f"Testing: {name}", "INFO")
            func()
            self.passed += 1
            self.log(f"✓ {name}", "PASS")
        except AssertionError as e:
            self.failed += 1
            error_msg = f"✗ {name}: {str(e)}"
            self.log(error_msg, "FAIL")
            self.errors.append(error_msg)
        except Exception as e:
            self.failed += 1
            error_msg = f"✗ {name}: Unexpected error: {str(e)}"
            self.log(error_msg, "FAIL")
            self.errors.append(error_msg)
    
    def get(self, url, **kwargs):
        """Make authenticated GET request"""
        if self.access_token:
            headers = kwargs.get('headers', {})
            headers['Authorization'] = f'Bearer {self.access_token}'
            kwargs['headers'] = headers
        return self.session.get(url, **kwargs)
    
    def post(self, url, **kwargs):
        """Make authenticated POST request"""
        if self.access_token:
            headers = kwargs.get('headers', {})
            headers['Authorization'] = f'Bearer {self.access_token}'
            kwargs['headers'] = headers
        return self.session.post(url, **kwargs)
    
    def assert_status(self, response, expected_status, endpoint):
        """Assert response status code"""
        if response.status_code != expected_status:
            raise AssertionError(
                f"{endpoint} returned {response.status_code}, expected {expected_status}. "
                f"Response: {response.text[:200]}"
            )
    
    def assert_json(self, response, endpoint):
        """Assert response is valid JSON"""
        try:
            return response.json()
        except Exception as e:
            raise AssertionError(f"{endpoint} did not return valid JSON: {str(e)}")

# Initialize test runner
runner = TestRunner()

# Test 1: Root health check
def test_root_health():
    response = runner.session.get(f"{BASE_URL}/api/")
    runner.assert_status(response, 200, "GET /api/")
    data = runner.assert_json(response, "GET /api/")
    assert "app" in data and data["app"] == "Urban Dotted Expense Book"
    assert "status" in data and data["status"] == "ok"

runner.test("GET /api/ (root health)", test_root_health)

# Test 2: Login
def test_login():
    response = runner.session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    runner.assert_status(response, 200, "POST /api/auth/login")
    data = runner.assert_json(response, "POST /api/auth/login")
    assert "user_id" in data and "email" in data
    assert data["email"] == TEST_EMAIL.lower()
    assert len(data.get("business_ids", [])) > 0
    runner.business_id = data["business_ids"][0]
    
    # Extract access token for Bearer auth (workaround for secure cookies over HTTP)
    cookies = runner.session.cookies.get_dict()
    if 'access_token' in cookies:
        runner.access_token = cookies['access_token']
        runner.log(f"Using Bearer token auth (secure cookies workaround)", "INFO")

runner.test("POST /api/auth/login", test_login)

# Test 3: Get current user
def test_get_me():
    response = runner.get(f"{BASE_URL}/api/auth/me")
    runner.assert_status(response, 200, "GET /api/auth/me")
    data = runner.assert_json(response, "GET /api/auth/me")
    assert "user_id" in data and "email" in data

runner.test("GET /api/auth/me", test_get_me)

# Test 4: Get business
def test_get_business():
    response = runner.get(f"{BASE_URL}/api/business")
    runner.assert_status(response, 200, "GET /api/business")
    data = runner.assert_json(response, "GET /api/business")
    assert "business_id" in data and "name" in data

runner.test("GET /api/business", test_get_business)

# Test 5: List transactions
def test_list_transactions():
    response = runner.get(f"{BASE_URL}/api/transactions")
    runner.assert_status(response, 200, "GET /api/transactions")
    data = runner.assert_json(response, "GET /api/transactions")
    assert "items" in data and isinstance(data["items"], list)

runner.test("GET /api/transactions", test_list_transactions)

# Test 6: Get inventory
def test_get_inventory():
    response = runner.get(f"{BASE_URL}/api/inventory/purchases")
    runner.assert_status(response, 200, "GET /api/inventory/purchases")
    data = runner.assert_json(response, "GET /api/inventory/purchases")
    assert "items" in data and "totals" in data

runner.test("GET /api/inventory", test_get_inventory)

# Test 7: Get P&L
def test_get_pnl():
    response = runner.get(f"{BASE_URL}/api/pnl")
    runner.assert_status(response, 200, "GET /api/pnl")
    data = runner.assert_json(response, "GET /api/pnl")
    assert "fy" in data and "months" in data and "totals" in data

runner.test("GET /api/pnl", test_get_pnl)

# Test 8: Get reports P&L
def test_get_reports_pnl():
    response = runner.get(f"{BASE_URL}/api/reports/pnl")
    runner.assert_status(response, 200, "GET /api/reports/pnl")
    data = runner.assert_json(response, "GET /api/reports/pnl")
    assert "title" in data and "columns" in data and "rows" in data

runner.test("GET /api/reports/pnl", test_get_reports_pnl)

# Test 9: List documents
def test_list_documents():
    response = runner.get(f"{BASE_URL}/api/documents")
    runner.assert_status(response, 200, "GET /api/documents")
    data = runner.assert_json(response, "GET /api/documents")
    assert "items" in data and isinstance(data["items"], list)

runner.test("GET /api/documents", test_list_documents)

# Test 10: Upload and download document (validates LOCAL storage)
def test_document_upload_download():
    test_content = b"Test receipt for Urban Dotted Expense Book - Deployment Test"
    test_filename = f"test_receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # Upload
    files = {'file': (test_filename, io.BytesIO(test_content), 'text/plain')}
    data_form = {'notes': 'Automated deployment test'}
    response = runner.post(f"{BASE_URL}/api/documents/upload", files=files, data=data_form)
    runner.assert_status(response, 200, "POST /api/documents/upload")
    upload_data = runner.assert_json(response, "POST /api/documents/upload")
    assert "document_id" in upload_data and "storage_path" in upload_data
    document_id = upload_data["document_id"]
    runner.log(f"Uploaded document: {document_id}", "INFO")
    
    # Download and verify bytes match
    download_response = runner.get(f"{BASE_URL}/api/documents/{document_id}/download")
    runner.assert_status(download_response, 200, "GET /api/documents/{id}/download")
    assert download_response.content == test_content, "Downloaded bytes don't match uploaded"
    runner.log("✓ LOCAL storage validation: bytes match", "INFO")

runner.test("POST /api/documents/upload + download (LOCAL storage)", test_document_upload_download)

# Test 11: Get reminders
def test_get_reminders():
    response = runner.get(f"{BASE_URL}/api/reminders")
    runner.assert_status(response, 200, "GET /api/reminders")
    data = runner.assert_json(response, "GET /api/reminders")
    assert "items" in data and "counts" in data

runner.test("GET /api/reminders", test_get_reminders)

# Test 12: Get daily fields
def test_get_daily_fields():
    response = runner.get(f"{BASE_URL}/api/daily/fields")
    runner.assert_status(response, 200, "GET /api/daily/fields")
    data = runner.assert_json(response, "GET /api/daily/fields")
    assert "fields" in data and "sections" in data

runner.test("GET /api/daily/fields", test_get_daily_fields)

# Test 13: Get daily entry
def test_get_daily_entry():
    response = runner.get(f"{BASE_URL}/api/daily/entry")
    runner.assert_status(response, 200, "GET /api/daily/entry")
    data = runner.assert_json(response, "GET /api/daily/entry")
    assert "entry_date" in data and "fields" in data

runner.test("GET /api/daily/entry", test_get_daily_entry)

# Test 14: List reports
def test_list_reports():
    response = runner.session.get(f"{BASE_URL}/api/reports")
    runner.assert_status(response, 200, "GET /api/reports")
    data = runner.assert_json(response, "GET /api/reports")
    assert "reports" in data and len(data["reports"]) > 0

runner.test("GET /api/reports", test_list_reports)

# Test 15: Export transactions CSV
def test_export_transactions():
    response = runner.get(f"{BASE_URL}/api/export/transactions")
    runner.assert_status(response, 200, "GET /api/export/transactions")
    content_type = response.headers.get('content-type', '')
    assert 'text/csv' in content_type, f"Expected CSV, got: {content_type}"
    assert len(response.content) > 0

runner.test("GET /api/export/transactions", test_export_transactions)

# Test 16: Get dashboard
def test_get_dashboard():
    response = runner.get(f"{BASE_URL}/api/dashboard")
    runner.assert_status(response, 200, "GET /api/dashboard")
    data = runner.assert_json(response, "GET /api/dashboard")
    assert "kpis" in data and "months" in data

runner.test("GET /api/dashboard", test_get_dashboard)

# Test 17: Get GST
def test_get_gst():
    response = runner.get(f"{BASE_URL}/api/gst")
    runner.assert_status(response, 200, "GET /api/gst")
    data = runner.assert_json(response, "GET /api/gst")
    assert "totals" in data and "months" in data

runner.test("GET /api/gst", test_get_gst)

# Test 18: Get cashflow
def test_get_cashflow():
    response = runner.get(f"{BASE_URL}/api/cashflow")
    runner.assert_status(response, 200, "GET /api/cashflow")
    data = runner.assert_json(response, "GET /api/cashflow")
    assert "months" in data and "totals" in data

runner.test("GET /api/cashflow", test_get_cashflow)

# Test 19: Get COGS
def test_get_cogs():
    response = runner.get(f"{BASE_URL}/api/cogs")
    runner.assert_status(response, 200, "GET /api/cogs")
    data = runner.assert_json(response, "GET /api/cogs")
    assert "months" in data and "total_cogs" in data

runner.test("GET /api/cogs", test_get_cogs)

# Test 20: Get categories
def test_get_categories():
    response = runner.get(f"{BASE_URL}/api/categories")
    runner.assert_status(response, 200, "GET /api/categories")
    data = runner.assert_json(response, "GET /api/categories")
    assert "tree" in data and "flat" in data

runner.test("GET /api/categories", test_get_categories)

# Test 21: Get suppliers
def test_get_suppliers():
    response = runner.get(f"{BASE_URL}/api/suppliers")
    runner.assert_status(response, 200, "GET /api/suppliers")
    data = runner.assert_json(response, "GET /api/suppliers")
    assert isinstance(data, list)

runner.test("GET /api/suppliers", test_get_suppliers)

# Test 22: Get accounts
def test_get_accounts():
    response = runner.get(f"{BASE_URL}/api/accounts")
    runner.assert_status(response, 200, "GET /api/accounts")
    data = runner.assert_json(response, "GET /api/accounts")
    assert isinstance(data, list)

runner.test("GET /api/accounts", test_get_accounts)

# Test 23: Get assets
def test_get_assets():
    response = runner.get(f"{BASE_URL}/api/assets")
    runner.assert_status(response, 200, "GET /api/assets")
    data = runner.assert_json(response, "GET /api/assets")
    assert "items" in data and "totals" in data

runner.test("GET /api/assets", test_get_assets)

# Test 24: Get recurring
def test_get_recurring():
    response = runner.get(f"{BASE_URL}/api/recurring")
    runner.assert_status(response, 200, "GET /api/recurring")
    data = runner.assert_json(response, "GET /api/recurring")
    assert isinstance(data, list)

runner.test("GET /api/recurring", test_get_recurring)

# Test 25: Get month-end
def test_get_month_end():
    response = runner.get(f"{BASE_URL}/api/month-end")
    runner.assert_status(response, 200, "GET /api/month-end")
    data = runner.assert_json(response, "GET /api/month-end")
    assert "months" in data and "fy" in data

runner.test("GET /api/month-end", test_get_month_end)

# Test 26: Get year-end
def test_get_year_end():
    response = runner.get(f"{BASE_URL}/api/year-end")
    runner.assert_status(response, 200, "GET /api/year-end")
    data = runner.assert_json(response, "GET /api/year-end")
    assert "checks" in data and "ready_for_accountant" in data

runner.test("GET /api/year-end", test_get_year_end)

# Test 27: Accountant export ZIP
def test_accountant_export():
    export_data = {
        "fy": "FY2026-27",
        "reports": ["pnl", "gst", "ledger"],
        "format": "zip",
        "include_receipts": True
    }
    response = runner.post(f"{BASE_URL}/api/export/accountant", json=export_data)
    runner.assert_status(response, 200, "POST /api/export/accountant")
    assert response.headers.get('content-type') == 'application/zip'
    assert len(response.content) > 0
    runner.log(f"Accountant ZIP size: {len(response.content)} bytes", "INFO")

runner.test("POST /api/export/accountant (ZIP)", test_accountant_export)

# Print summary
print("\n" + "="*70)
print(f"{BLUE}DEPLOYMENT SMOKE TEST SUMMARY{RESET}")
print("="*70)
print(f"{GREEN}Passed: {runner.passed}{RESET}")
print(f"{RED}Failed: {runner.failed}{RESET}")
print(f"Total:  {runner.passed + runner.failed}")

if runner.errors:
    print(f"\n{RED}FAILED TESTS:{RESET}")
    for error in runner.errors:
        print(f"  {error}")
else:
    print(f"\n{GREEN}✓ All deployment smoke tests passed!{RESET}")
    print(f"{GREEN}✓ LOCAL storage backend validated (upload/download bytes match){RESET}")
    print(f"{GREEN}✓ No Emergent integrations tested (as requested){RESET}")

print("="*70)

sys.exit(0 if runner.failed == 0 else 1)
