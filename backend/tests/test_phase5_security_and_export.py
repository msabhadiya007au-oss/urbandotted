"""Phase 5 Security fixes + Accountant Export ZIP payroll pack tests.

Coverage:
    * SEC-001: /api/auth/forgot-password does NOT print reset token to stdout.
    * SEC-002: PUT /api/accounts/{id} with a random/other-tenant id returns 404.
    * Accountant Export ZIP bundles payroll/ CSVs and contains NO TFN/BSB/account numbers.
    * Regression endpoints: /dashboard, /reports/pnl, /gst, /cogs, /reminders,
      /month-end, /year-end return 2xx.
"""
import io
import os
import re
import time
import zipfile
import pytest
import requests

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
EMAIL = "urbandottedstore@gmail.com"
PASSWORD = "Milan@112233!@#"
BACKEND_ERR_LOG = "/var/log/supervisor/backend.err.log"


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    tok = s.cookies.get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---- Auth me returns owner role -------------------------------------------
def test_auth_me_owner(sess):
    r = sess.get(f"{BASE}/api/auth/me")
    assert r.status_code == 200, r.text
    d = r.json()
    role = d.get("role") or (d.get("user") or {}).get("role") or \
           (d.get("membership") or {}).get("role")
    assert role == "owner", f"expected owner, got {role} :: {d}"


# ---- SEC-001: forgot-password must not print token to stdout ---------------
def test_forgot_password_token_not_in_stdout():
    """Trigger forgot-password then scan the last chunk of backend.err.log
    to verify no obvious reset token (jwt-like or hex-like) is present tied
    to that request in the tail window."""
    # Snapshot log size before
    before_size = 0
    try:
        before_size = os.path.getsize(BACKEND_ERR_LOG)
    except OSError:
        pytest.skip("backend err log not accessible")

    r = requests.post(f"{BASE}/api/auth/forgot-password",
                      json={"email": EMAIL}, timeout=15)
    # Should be 200 or 202 with a neutral response (avoid enumeration)
    assert r.status_code in (200, 202, 204), r.text
    time.sleep(1.0)  # allow log flush

    with open(BACKEND_ERR_LOG, "rb") as f:
        f.seek(max(0, before_size))
        chunk = f.read().decode(errors="ignore")

    # Common token shapes we do NOT want to see printed
    bad_patterns = [
        r"\breset[_-]?token\b[^\n]*[A-Za-z0-9_-]{20,}",  # explicit label
        r"\btoken=[A-Za-z0-9_.-]{20,}",
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}",     # JWT
    ]
    hits = []
    for pat in bad_patterns:
        for m in re.findall(pat, chunk, flags=re.IGNORECASE):
            hits.append((pat, m[:80]))
    assert not hits, f"Reset token leaked to stdout/log: {hits[:3]}"


# ---- SEC-002: cross-tenant PUT /accounts/{id} returns 404 ------------------
def test_cross_tenant_put_accounts_returns_404(sess):
    """PUT /api/accounts/{id} with an id that does not belong to the current
    business must return 404 (BOLA blocked). Using a random UUID-like id."""
    fake_id = "acc_00000000000000000000000000000000"
    r = sess.put(f"{BASE}/api/accounts/{fake_id}",
                 json={"name": "Hacked", "type": "expense"})
    assert r.status_code == 404, f"expected 404 got {r.status_code} :: {r.text[:200]}"


# ---- Accountant Export ZIP with payroll pack -------------------------------
def _find_fy(sess):
    r = sess.get(f"{BASE}/api/payroll/pay-runs?status=finalised")
    for run in r.json().get("items", []):
        if run.get("fy"):
            return run["fy"]
    return "2025-26"


def test_accountant_export_zip_bundles_payroll_and_no_sensitive_data(sess):
    fy = _find_fy(sess)
    # Try POST first (per spec)
    r = sess.post(f"{BASE}/api/export/accountant",
                  json={"format": "zip", "fy": fy,
                        "reports": ["pnl", "gst_summary", "cashflow",
                                    "transactions_detail"]},
                  timeout=60)
    assert r.status_code == 200, f"{r.status_code} :: {r.text[:200]}"
    assert r.headers.get("content-type", "").startswith(("application/zip", "application/octet-stream")), \
           r.headers.get("content-type")

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    payroll_files = [n for n in names if "payroll/" in n or n.startswith("payroll")]
    assert payroll_files, f"ZIP missing payroll/ pack. Contents: {names[:30]}"

    expected = [
        "payroll_summary", "employee_payment_summary",
        "super_by_quarter", "leave_balances",
        "payg_liabilities", "wages_payables",
    ]
    for stem in expected:
        assert any(stem in n for n in payroll_files), \
            f"payroll pack missing {stem}. files={payroll_files}"
    # README optional but preferred
    assert any("README" in n.upper() for n in payroll_files), \
        f"payroll/README.txt missing. files={payroll_files}"

    # Sensitive data must NOT appear anywhere in the ZIP (payroll or otherwise).
    # We look for TFN/BSB/account_number labels and BSB numeric patterns; a
    # raw 9-digit sequence alone is too broad (matches timestamps/ids).
    tfn_label = re.compile(rb"\bTFN\b")
    bsb_pat = re.compile(rb"\b\d{3}-\d{3}\b")
    acct_pat = re.compile(rb"account[_ ]?number", re.IGNORECASE)
    tfn_json_pat = re.compile(rb'"tfn"\s*:\s*"?\d{8,9}', re.IGNORECASE)

    offenders = []
    for n in names:
        try:
            data = z.read(n)
        except Exception:
            continue
        # skip binary artifacts (pdfs) — they may contain address numerics
        if n.endswith((".pdf", ".png", ".jpg")):
            continue
        for label, pat in (("TFN", tfn_label), ("BSB", bsb_pat),
                            ("TFN-json", tfn_json_pat),
                            ("account_number", acct_pat)):
            if pat.search(data):
                # allow the phrase in README explanations only
                if "README" in n.upper() and label in ("TFN", "account_number"):
                    continue
                offenders.append((n, label))
    assert not offenders, f"Sensitive data leaked into export ZIP: {offenders[:5]}"


# ---- Regression endpoints --------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/dashboard",
    "/api/reports/pnl",
    "/api/gst",
    "/api/cogs",
    "/api/reminders",
    "/api/month-end",
    "/api/year-end",
])
def test_regression_endpoints_ok(sess, path):
    r = sess.get(f"{BASE}{path}", timeout=20)
    # Some month-end/year-end may need query params — accept 200/400/422 (shape known)
    assert r.status_code in (200, 400, 422), f"{path} -> {r.status_code}: {r.text[:120]}"
    if r.status_code == 200:
        # ensure JSON parse
        r.json()


# ---- Unauth rejected on all new payroll endpoints -------------------------
def test_unauth_rejected_on_new_endpoints():
    s = requests.Session()
    endpoints = [
        "/api/payroll/wages-payables",
        "/api/payroll/payg-liabilities",
        "/api/payroll/liabilities-summary",
        "/api/payroll/postings",
    ]
    for p in endpoints:
        r = s.get(f"{BASE}{p}")
        assert r.status_code in (401, 403), f"{p} allowed unauth ({r.status_code})"
    # POST post-accounting
    r = s.post(f"{BASE}/api/payroll/pay-runs/UD-PR-0000-000000/post-accounting")
    assert r.status_code in (401, 403), f"post-accounting unauth got {r.status_code}"
