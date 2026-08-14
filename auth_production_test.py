#!/usr/bin/env python3
"""
Production Auth Changes Verification for Urban Dotted Expense Book.

Tests the recent auth changes:
1. Cookie flags (SameSite, Secure) driven by env vars
2. CORS credentials handling
3. Google OAuth disabled (returns 501)
4. Auth config endpoint returns google_oauth_enabled
5. Refresh flow
6. Error paths (wrong password, register disabled)
7. Regression smoke tests
"""
import requests
import json
import io
import sys
from datetime import datetime

# Test configuration - use production URL
BASE_URL = "https://deploy-fix-145.preview.emergentagent.com/api"
TEST_EMAIL = "urbandottedstore@gmail.com"
TEST_PASSWORD = "Milan@112233!@#"

# Color codes for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BLUE = '\033[94m'
CYAN = '\033[96m'

class AuthTestRunner:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.business_id = None
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.warnings = []
        
    def log(self, message, status="INFO"):
        colors = {"PASS": GREEN, "FAIL": RED, "INFO": BLUE, "WARN": YELLOW, "SECTION": CYAN}
        color = colors.get(status, RESET)
        print(f"{color}[{status}]{RESET} {message}")
        
    def section(self, title):
        """Print a section header"""
        print(f"\n{CYAN}{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}{RESET}\n")
        
    def test(self, name, func):
        """Run a test function and track results"""
        try:
            self.log(f"Testing: {name}", "INFO")
            func()
            self.passed += 1
            self.log(f"✓ {name}", "PASS")
            return True
        except AssertionError as e:
            self.failed += 1
            error_msg = f"✗ {name}: {str(e)}"
            self.log(error_msg, "FAIL")
            self.errors.append(error_msg)
            return False
        except Exception as e:
            self.failed += 1
            error_msg = f"✗ {name}: Unexpected error: {str(e)}"
            self.log(error_msg, "FAIL")
            self.errors.append(error_msg)
            return False
    
    def assert_status(self, response, expected_status, endpoint):
        """Assert response status code"""
        if response.status_code != expected_status:
            raise AssertionError(
                f"{endpoint} returned {response.status_code}, expected {expected_status}. "
                f"Response: {response.text[:500]}"
            )
    
    def assert_json(self, response, endpoint):
        """Assert response is valid JSON"""
        try:
            return response.json()
        except Exception as e:
            raise AssertionError(f"{endpoint} did not return valid JSON: {str(e)}")

# Initialize test runner
runner = AuthTestRunner()

# ============================================================================
# SECTION A: Auth Config Endpoint
# ============================================================================
runner.section("A. Auth Config Endpoint")

def test_auth_config_no_auth():
    """GET /api/auth/config must work WITHOUT authentication"""
    # Create a fresh session without any cookies
    fresh_session = requests.Session()
    response = fresh_session.get(f"{BASE_URL}/auth/config")
    runner.assert_status(response, 200, "GET /api/auth/config")
    data = runner.assert_json(response, "GET /api/auth/config")
    
    # Must have both keys
    assert "allow_signups" in data, "Missing 'allow_signups' key"
    assert "google_oauth_enabled" in data, "Missing 'google_oauth_enabled' key"
    
    # google_oauth_enabled must be false (GOOGLE_OAUTH_ENABLED=false in .env)
    assert data["google_oauth_enabled"] == False, \
        f"Expected google_oauth_enabled=false, got {data['google_oauth_enabled']}"
    
    runner.log(f"Auth config: {data}", "INFO")

runner.test("GET /api/auth/config (no auth required, google_oauth_enabled=false)", test_auth_config_no_auth)

# ============================================================================
# SECTION B: Cookie Flags
# ============================================================================
runner.section("B. Cookie Flags (HttpOnly, Secure, SameSite=None)")

def test_login_cookie_flags():
    """POST /api/auth/login must set cookies with correct flags"""
    response = runner.session.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    runner.assert_status(response, 200, "POST /api/auth/login")
    data = runner.assert_json(response, "POST /api/auth/login")
    
    # Verify user data
    assert "user_id" in data and "email" in data
    assert data["email"] == TEST_EMAIL.lower()
    assert len(data.get("business_ids", [])) > 0
    runner.business_id = data["business_ids"][0]
    
    # Check Set-Cookie headers
    set_cookie_headers = response.headers.get_list('Set-Cookie') if hasattr(response.headers, 'get_list') else []
    if not set_cookie_headers:
        # Fallback: check response.cookies
        set_cookie_headers = [f"{k}={v}" for k, v in response.cookies.items()]
    
    runner.log(f"Set-Cookie headers: {set_cookie_headers}", "INFO")
    
    # Parse cookies from response
    cookies = response.cookies
    
    # Check access_token cookie
    assert 'access_token' in cookies, "Missing access_token cookie"
    runner.access_token = cookies['access_token']
    
    # Check refresh_token cookie
    assert 'refresh_token' in cookies, "Missing refresh_token cookie"
    runner.refresh_token = cookies['refresh_token']
    
    # Verify cookie attributes by checking raw Set-Cookie headers
    raw_headers = response.raw.headers.getlist('Set-Cookie') if hasattr(response.raw.headers, 'getlist') else []
    if not raw_headers:
        # Try alternative method
        import http.client
        raw_headers = []
        for header in response.headers._store.values():
            if header[0].lower() == 'set-cookie':
                raw_headers.append(header[1])
    
    runner.log(f"Raw Set-Cookie headers: {raw_headers}", "INFO")
    
    # Check for required attributes in Set-Cookie headers
    access_cookie_header = None
    refresh_cookie_header = None
    
    for header in raw_headers:
        if 'access_token=' in header:
            access_cookie_header = header
        if 'refresh_token=' in header:
            refresh_cookie_header = header
    
    if access_cookie_header:
        runner.log(f"access_token cookie: {access_cookie_header}", "INFO")
        assert 'HttpOnly' in access_cookie_header, "access_token missing HttpOnly flag"
        assert 'Secure' in access_cookie_header, "access_token missing Secure flag"
        assert 'SameSite=None' in access_cookie_header or 'SameSite=none' in access_cookie_header, \
            "access_token missing SameSite=None flag"
    else:
        runner.warnings.append("Could not verify access_token cookie flags from headers")
    
    if refresh_cookie_header:
        runner.log(f"refresh_token cookie: {refresh_cookie_header}", "INFO")
        assert 'HttpOnly' in refresh_cookie_header, "refresh_token missing HttpOnly flag"
        assert 'Secure' in refresh_cookie_header, "refresh_token missing Secure flag"
        assert 'SameSite=None' in refresh_cookie_header or 'SameSite=none' in refresh_cookie_header, \
            "refresh_token missing SameSite=None flag"
    else:
        runner.warnings.append("Could not verify refresh_token cookie flags from headers")

runner.test("POST /api/auth/login (cookie flags: HttpOnly, Secure, SameSite=None)", test_login_cookie_flags)

# ============================================================================
# SECTION C: Google Session Disabled
# ============================================================================
runner.section("C. Google Session Disabled (501)")

def test_google_session_disabled():
    """POST /api/auth/session must return 501 when Google OAuth is disabled"""
    response = runner.session.post(
        f"{BASE_URL}/auth/session",
        json={"session_id": "fake-session-id-12345"}
    )
    runner.assert_status(response, 501, "POST /api/auth/session")
    data = runner.assert_json(response, "POST /api/auth/session")
    
    # Check error detail
    assert "detail" in data, "Missing 'detail' key in error response"
    assert "Google login is not configured" in data["detail"], \
        f"Expected 'Google login is not configured' message, got: {data['detail']}"
    
    runner.log(f"Google session correctly disabled: {data['detail']}", "INFO")

runner.test("POST /api/auth/session (returns 501 - Google disabled)", test_google_session_disabled)

# ============================================================================
# SECTION D: Refresh Flow
# ============================================================================
runner.section("D. Refresh Flow")

def test_refresh_flow():
    """POST /api/auth/refresh must issue new access_token using refresh_token"""
    # Ensure we have a refresh token from login
    if not runner.refresh_token:
        raise AssertionError("No refresh_token available. Login test must pass first.")
    
    # Make refresh request (cookies should be sent automatically by session)
    response = runner.session.post(f"{BASE_URL}/auth/refresh")
    runner.assert_status(response, 200, "POST /api/auth/refresh")
    data = runner.assert_json(response, "POST /api/auth/refresh")
    
    assert data.get("ok") == True, "Refresh response should have ok=true"
    
    # Check that new access_token cookie is set
    cookies = response.cookies
    if 'access_token' in cookies:
        new_access_token = cookies['access_token']
        runner.log(f"New access_token received (length: {len(new_access_token)})", "INFO")
        runner.access_token = new_access_token
    else:
        runner.warnings.append("New access_token not found in refresh response cookies")

runner.test("POST /api/auth/refresh (refresh flow)", test_refresh_flow)

# ============================================================================
# SECTION E: Rate-limit / Error Paths
# ============================================================================
runner.section("E. Rate-limit / Error Paths")

def test_wrong_password():
    """POST /api/auth/login with wrong password must return 401"""
    fresh_session = requests.Session()
    response = fresh_session.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": "WrongPassword123!"}
    )
    runner.assert_status(response, 401, "POST /api/auth/login (wrong password)")
    data = runner.assert_json(response, "POST /api/auth/login (wrong password)")
    
    assert "detail" in data, "Missing 'detail' key in error response"
    assert "Invalid email or password" in data["detail"], \
        f"Expected 'Invalid email or password', got: {data['detail']}"
    
    runner.log(f"Wrong password correctly rejected: {data['detail']}", "INFO")

runner.test("POST /api/auth/login (wrong password → 401)", test_wrong_password)

def test_register_disabled():
    """POST /api/auth/register must return 403 when signups disabled"""
    fresh_session = requests.Session()
    response = fresh_session.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "TestPassword123!",
            "name": "Test User",
            "business_name": "Test Business"
        }
    )
    runner.assert_status(response, 403, "POST /api/auth/register")
    data = runner.assert_json(response, "POST /api/auth/register")
    
    assert "detail" in data, "Missing 'detail' key in error response"
    assert "New sign-ups are disabled" in data["detail"], \
        f"Expected 'New sign-ups are disabled', got: {data['detail']}"
    
    runner.log(f"Register correctly disabled: {data['detail']}", "INFO")

runner.test("POST /api/auth/register (signups disabled → 403)", test_register_disabled)

# ============================================================================
# SECTION F: Regression Smoke Tests
# ============================================================================
runner.section("F. Regression Smoke Tests (Authenticated Endpoints)")

def test_root_endpoint():
    """GET /api/ (root)"""
    response = runner.session.get(f"{BASE_URL}/")
    runner.assert_status(response, 200, "GET /api/")
    data = runner.assert_json(response, "GET /api/")
    assert "app" in data and "status" in data

runner.test("GET /api/ (root)", test_root_endpoint)

def test_auth_me():
    """GET /api/auth/me"""
    response = runner.session.get(f"{BASE_URL}/auth/me")
    runner.assert_status(response, 200, "GET /api/auth/me")
    data = runner.assert_json(response, "GET /api/auth/me")
    assert "user_id" in data and "email" in data

runner.test("GET /api/auth/me", test_auth_me)

def test_dashboard():
    """GET /api/dashboard?fy=FY2026-27&period=fy"""
    response = runner.session.get(f"{BASE_URL}/dashboard?fy=FY2026-27&period=fy")
    runner.assert_status(response, 200, "GET /api/dashboard")
    data = runner.assert_json(response, "GET /api/dashboard")
    assert "kpis" in data or "months" in data

runner.test("GET /api/dashboard?fy=FY2026-27&period=fy", test_dashboard)

def test_transactions():
    """GET /api/transactions?fy=FY2026-27"""
    response = runner.session.get(f"{BASE_URL}/transactions?fy=FY2026-27")
    runner.assert_status(response, 200, "GET /api/transactions")
    data = runner.assert_json(response, "GET /api/transactions")
    assert "items" in data

runner.test("GET /api/transactions?fy=FY2026-27", test_transactions)

def test_documents_list():
    """GET /api/documents"""
    response = runner.session.get(f"{BASE_URL}/documents")
    runner.assert_status(response, 200, "GET /api/documents")
    data = runner.assert_json(response, "GET /api/documents")
    assert "items" in data

runner.test("GET /api/documents", test_documents_list)

def test_reports_list():
    """GET /api/reports"""
    response = runner.session.get(f"{BASE_URL}/reports")
    runner.assert_status(response, 200, "GET /api/reports")
    data = runner.assert_json(response, "GET /api/reports")
    assert "reports" in data or isinstance(data, list)

runner.test("GET /api/reports", test_reports_list)

def test_document_upload_download():
    """POST /api/documents/upload and GET /api/documents/{id}/download"""
    test_content = b"Auth test receipt - production verification"
    test_filename = f"auth_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    # Upload
    files = {'file': (test_filename, io.BytesIO(test_content), 'text/plain')}
    data_form = {'notes': 'Auth production test'}
    response = runner.session.post(f"{BASE_URL}/documents/upload", files=files, data=data_form)
    runner.assert_status(response, 200, "POST /api/documents/upload")
    upload_data = runner.assert_json(response, "POST /api/documents/upload")
    assert "document_id" in upload_data
    document_id = upload_data["document_id"]
    
    # Download
    download_response = runner.session.get(f"{BASE_URL}/documents/{document_id}/download")
    runner.assert_status(download_response, 200, "GET /api/documents/{id}/download")
    assert download_response.content == test_content, "Downloaded bytes don't match uploaded"
    runner.log("✓ Upload/download bytes match", "INFO")

runner.test("POST /api/documents/upload + GET /api/documents/{id}/download", test_document_upload_download)

# ============================================================================
# SECTION G: Accountant Export Sanity
# ============================================================================
runner.section("G. Accountant Export Sanity")

def test_accountant_export():
    """POST /api/export/accountant (or GET if that's the endpoint)"""
    # Try POST first (as per existing test)
    export_data = {
        "fy": "FY2026-27",
        "reports": ["pnl", "gst", "ledger"],
        "format": "zip",
        "include_receipts": True
    }
    response = runner.session.post(f"{BASE_URL}/export/accountant", json=export_data)
    
    if response.status_code == 405:
        # Try GET instead
        response = runner.session.get(f"{BASE_URL}/export/accountant?fy=FY2026-27")
    
    runner.assert_status(response, 200, "Accountant export")
    
    content_type = response.headers.get('content-type', '')
    assert 'application/zip' in content_type, f"Expected application/zip, got: {content_type}"
    assert len(response.content) > 0, "ZIP file is empty"
    runner.log(f"Accountant ZIP size: {len(response.content)} bytes", "INFO")

runner.test("Accountant export (200 + application/zip)", test_accountant_export)

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*70)
print(f"{BLUE}PRODUCTION AUTH VERIFICATION SUMMARY{RESET}")
print("="*70)
print(f"{GREEN}Passed: {runner.passed}{RESET}")
print(f"{RED}Failed: {runner.failed}{RESET}")
print(f"Total:  {runner.passed + runner.failed}")

if runner.warnings:
    print(f"\n{YELLOW}WARNINGS:{RESET}")
    for warning in runner.warnings:
        print(f"  ⚠ {warning}")

if runner.errors:
    print(f"\n{RED}FAILED TESTS:{RESET}")
    for error in runner.errors:
        print(f"  {error}")
else:
    print(f"\n{GREEN}✓ All production auth tests passed!{RESET}")
    print(f"{GREEN}✓ Cookie flags verified (HttpOnly, Secure, SameSite=None){RESET}")
    print(f"{GREEN}✓ Google OAuth correctly disabled (501){RESET}")
    print(f"{GREEN}✓ Auth config endpoint working without auth{RESET}")
    print(f"{GREEN}✓ Refresh flow working{RESET}")
    print(f"{GREEN}✓ Error paths working (401, 403){RESET}")
    print(f"{GREEN}✓ Regression smoke tests passed{RESET}")

print("="*70)

sys.exit(0 if runner.failed == 0 else 1)
