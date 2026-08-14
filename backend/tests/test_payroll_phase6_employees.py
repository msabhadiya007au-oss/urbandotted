"""Phase-6 Employee Profile & Management backend integration tests.

Covers:
  * Auth session with the shipped owner credentials
  * GET /payroll/employees returns current_pay_basis / current_pay_frequency
  * Status filter (active/terminated/all/default hides archived)
  * /employees/check-duplicate (email, mobile last-8, first+last+dob)
  * POST /employees 409 duplicate → then force=true creates
  * employment_periods initialised (single open period)
  * Terminate → closes open period, top-level markers set, double-terminate 400
  * Rehire on active → 400; on terminated → new period, status active
  * GET /employees/{id}/history
  * PUT /employees/{id} persists all extended fields; cannot overwrite periods
  * TFN encrypt on PUT tax, GET returns has_tfn+tfn_masked, reveal_tfn=true returns plaintext
  * TFN sending '' does NOT wipe existing tfn_enc
  * Documents linked_type=employee upload, list-filter, delete (soft), doc_ids appended
  * Regression: /dashboard, /reports/pnl, /gst, /cogs shapes unchanged
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # Fallback to frontend/.env (running inside container without env var propagated)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
                break

EMAIL = "urbandottedstore@gmail.com"
PASSWORD = "Milan@112233!@#"

MIN_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


# ---------- fixtures ----------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    me = sess.get(f"{BASE}/api/auth/me", timeout=15)
    assert me.status_code == 200, f"/auth/me failed: {me.status_code} {me.text}"
    return sess


@pytest.fixture(scope="session")
def emp(s):
    """Create a fresh Phase 6 test employee (force=true to bypass any prior duplicates)."""
    tag = uuid.uuid4().hex[:6]
    payload = {
        "first_name": "PhaseSix",
        "last_name": f"Test{tag}",
        "dob": "1990-01-15",
        "email": f"test-phase6-{tag}@example.com",
        "mobile": f"04{int(tag, 16) % 100000000:08d}",
        "employment_start_date": "2024-01-10",
        "job_title": "Tester",
        "employment_type": "full_time",
    }
    r = s.post(f"{BASE}/api/payroll/employees?force=true", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    doc = r.json()
    yield doc, payload
    # Cleanup: archive
    try:
        s.delete(f"{BASE}/api/payroll/employees/{doc['employee_id']}", timeout=10)
    except Exception:
        pass


# ---------- basic auth ----------
def test_auth_me(s):
    r = s.get(f"{BASE}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data.get("email", "").lower() == EMAIL
    assert data.get("role") == "owner"


# ---------- list + current pay fields ----------
def test_list_employees_has_current_pay_fields(s):
    r = s.get(f"{BASE}/api/payroll/employees")
    assert r.status_code == 200
    items = r.json()["items"]
    assert isinstance(items, list) and len(items) > 0
    e = items[0]
    assert "current_pay_basis" in e
    assert "current_pay_frequency" in e


def test_status_filter_terminated_and_all(s):
    r_all = s.get(f"{BASE}/api/payroll/employees?status=all")
    r_term = s.get(f"{BASE}/api/payroll/employees?status=terminated")
    r_def = s.get(f"{BASE}/api/payroll/employees")
    assert r_all.status_code == r_term.status_code == r_def.status_code == 200
    all_items = r_all.json()["items"]
    term_items = r_term.json()["items"]
    def_items = r_def.json()["items"]
    # default hides archived
    for e in def_items:
        assert e.get("status") != "archived"
    # terminated filter only returns terminated
    for e in term_items:
        assert e["status"] == "terminated"
    # 'all' is at least as big as default
    assert len(all_items) >= len(def_items)


# ---------- duplicate detection ----------
def test_check_duplicate_by_email(s, emp):
    doc, payload = emp
    r = s.post(f"{BASE}/api/payroll/employees/check-duplicate",
               json={"email": payload["email"].upper()})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(m["employee_id"] == doc["employee_id"] for m in body["matches"])


def test_check_duplicate_by_mobile_last8(s, emp):
    doc, payload = emp
    partial_mob = "9999" + payload["mobile"][-8:]
    r = s.post(f"{BASE}/api/payroll/employees/check-duplicate",
               json={"mobile": partial_mob})
    assert r.status_code == 200
    ids = [m["employee_id"] for m in r.json()["matches"]]
    assert doc["employee_id"] in ids


def test_check_duplicate_by_name_dob(s, emp):
    doc, payload = emp
    r = s.post(f"{BASE}/api/payroll/employees/check-duplicate", json={
        "first_name": payload["first_name"],
        "last_name": payload["last_name"],
        "dob": payload["dob"],
    })
    assert r.status_code == 200
    ids = [m["employee_id"] for m in r.json()["matches"]]
    assert doc["employee_id"] in ids


def test_post_employee_409_then_force(s, emp):
    doc, payload = emp
    tag = uuid.uuid4().hex[:6]
    dup_payload = {**payload, "first_name": "PhaseSixDup", "last_name": f"Dup{tag}",
                   "mobile": f"04{uuid.uuid4().hex[:8]}"}  # same email as existing
    r = s.post(f"{BASE}/api/payroll/employees", json=dup_payload)
    assert r.status_code == 409, r.text
    body = r.json()["detail"]
    assert body["code"] == "possible_duplicate"
    assert isinstance(body["matches"], list) and len(body["matches"]) >= 1
    # Now force
    r2 = s.post(f"{BASE}/api/payroll/employees?force=true", json=dup_payload)
    assert r2.status_code == 200
    new_id = r2.json()["employee_id"]
    # cleanup
    s.delete(f"{BASE}/api/payroll/employees/{new_id}")


# ---------- employment_periods ----------
def test_employment_periods_initialised(emp):
    doc, _ = emp
    periods = doc.get("employment_periods")
    assert isinstance(periods, list) and len(periods) == 1
    assert periods[0]["end_date"] is None
    assert periods[0]["start_date"] == doc["employment_start_date"]


# ---------- terminate / rehire / history ----------
def test_terminate_and_rehire_cycle(s):
    tag = uuid.uuid4().hex[:6]
    r = s.post(f"{BASE}/api/payroll/employees?force=true", json={
        "first_name": "PhaseSix", "last_name": f"Term{tag}",
        "email": f"test-phase6-term-{tag}@example.com",
        "mobile": f"04{uuid.uuid4().hex[:8]}",
        "employment_start_date": "2024-02-01",
        "employment_type": "full_time",
    })
    assert r.status_code == 200
    eid = r.json()["employee_id"]
    try:
        # Rehire when active → 400
        rr = s.post(f"{BASE}/api/payroll/employees/{eid}/rehire",
                    json={"start_date": "2025-01-01"})
        assert rr.status_code == 400

        # Terminate
        tr = s.post(f"{BASE}/api/payroll/employees/{eid}/terminate", json={
            "termination_date": "2025-01-31", "reason": "resigned", "note": "left for study"
        })
        assert tr.status_code == 200, tr.text

        prof = s.get(f"{BASE}/api/payroll/employees/{eid}").json()
        assert prof["status"] == "terminated"
        assert prof["termination_reason"] == "resigned"
        assert prof["terminated_at"]
        periods = prof["employment_periods"]
        assert len(periods) == 1
        assert periods[0]["end_date"] == "2025-01-31"
        assert periods[0]["termination_reason"] == "resigned"

        # Second terminate → 400
        tr2 = s.post(f"{BASE}/api/payroll/employees/{eid}/terminate", json={
            "termination_date": "2025-02-01"
        })
        assert tr2.status_code == 400

        # Rehire
        rh = s.post(f"{BASE}/api/payroll/employees/{eid}/rehire", json={
            "start_date": "2025-06-01", "employment_type": "part_time", "job_title": "Rehired Role"
        })
        assert rh.status_code == 200, rh.text

        prof2 = s.get(f"{BASE}/api/payroll/employees/{eid}").json()
        assert prof2["status"] == "active"
        assert prof2["employment_start_date"] == "2025-06-01"
        assert prof2["employment_type"] == "part_time"
        assert prof2["job_title"] == "Rehired Role"
        assert prof2.get("terminated_at") in (None, "")
        assert len(prof2["employment_periods"]) == 2
        assert prof2["employment_periods"][0]["end_date"] == "2025-01-31"  # closed
        assert prof2["employment_periods"][1]["end_date"] is None          # open

        # /history endpoint
        h = s.get(f"{BASE}/api/payroll/employees/{eid}/history").json()
        assert h["employee_id"] == eid
        assert len(h["periods"]) == 2
    finally:
        s.delete(f"{BASE}/api/payroll/employees/{eid}")


# ---------- PUT employee persists extended fields, cannot overwrite periods ----------
def test_put_employee_extended_fields(s, emp):
    doc, payload = emp
    eid = doc["employee_id"]
    body = {
        "first_name": payload["first_name"],
        "last_name": payload["last_name"],
        "email": payload["email"],
        "mobile": payload["mobile"],
        "dob": payload["dob"],
        "employment_start_date": payload["employment_start_date"],
        "employment_type": "full_time",
        "job_title": "Updated Title",
        "address": "1 Test St",
        "address_line_2": "Unit 5",
        "suburb": "Adelaide",
        "state": "SA",
        "postcode": "5000",
        "postal_same_as_residential": False,
        "postal_address": "PO Box 99",
        "postal_suburb": "Norwood",
        "postal_state": "SA",
        "postal_postcode": "5067",
        "emergency_contact_name": "Jane Doe",
        "emergency_contact_mobile": "0499000111",
        "probation_end_date": "2024-04-10",
        "std_hours_per_day": "7.6",
        "std_hours_per_week": "38",
        "std_hours_per_fortnight": "76",
        "std_hours_per_month": "164.6",
        "pattern_mon_hours": "7.6",
        "pattern_tue_hours": "7.6",
        "pattern_wed_hours": "7.6",
        "pattern_thu_hours": "7.6",
        "pattern_fri_hours": "7.6",
        "notes": "Test notes",
        "work_email": "work@example.com",
        "alt_phone": "0388000000",
        # Attempt to overwrite periods → should be ignored (not present in EmployeeIn)
    }
    # Sneak an employment_periods key — Pydantic will silently drop extras
    r = s.put(f"{BASE}/api/payroll/employees/{eid}", json={**body, "employment_periods": []})
    assert r.status_code == 200, r.text
    got = s.get(f"{BASE}/api/payroll/employees/{eid}").json()
    assert got["job_title"] == "Updated Title"
    assert got["address_line_2"] == "Unit 5"
    assert got["postal_address"] == "PO Box 99"
    assert got["postal_postcode"] == "5067"
    assert got["emergency_contact_name"] == "Jane Doe"
    assert got["probation_end_date"] == "2024-04-10"
    assert got["std_hours_per_week"] == "38"
    assert got["pattern_wed_hours"] == "7.6"
    assert got["notes"] == "Test notes"
    assert got["work_email"] == "work@example.com"
    # Periods untouched (still 1 open period)
    assert isinstance(got["employment_periods"], list) and len(got["employment_periods"]) == 1


# ---------- TFN ----------
def test_tfn_encrypt_mask_reveal(s, emp):
    eid = emp[0]["employee_id"]
    r = s.put(f"{BASE}/api/payroll/employees/{eid}/tax", json={
        "payg_enabled": True, "tax_free_threshold": True, "australian_resident": True,
        "help_loan": False, "tfn": "123456789", "tfn_declared": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tfn_enc" not in body   # never leak
    assert body.get("tfn_masked", "").endswith("789")

    g = s.get(f"{BASE}/api/payroll/employees/{eid}/tax").json()
    assert g["has_tfn"] is True
    assert g["tfn_masked"].endswith("789")
    assert "tfn" not in g

    # Reveal
    g2 = s.get(f"{BASE}/api/payroll/employees/{eid}/tax?reveal_tfn=true").json()
    assert g2.get("tfn") == "123456789"


def test_tfn_empty_does_not_wipe(s, emp):
    eid = emp[0]["employee_id"]
    # First set it
    s.put(f"{BASE}/api/payroll/employees/{eid}/tax", json={"tfn": "987654321"})
    # Send empty string — must NOT wipe
    r = s.put(f"{BASE}/api/payroll/employees/{eid}/tax", json={"tfn": "", "tfn_declared": True})
    assert r.status_code == 200
    g = s.get(f"{BASE}/api/payroll/employees/{eid}/tax?reveal_tfn=true").json()
    assert g.get("tfn") == "987654321"
    assert g["has_tfn"] is True


# ---------- Documents linked to employee ----------
def test_documents_employee_upload_list_delete(s, emp):
    eid = emp[0]["employee_id"]
    files = {"file": ("test.pdf", io.BytesIO(MIN_PDF), "application/pdf")}
    data = {"linked_type": "employee", "linked_id": eid, "notes": "test-phase6-doc"}
    r = s.post(f"{BASE}/api/documents/upload", files=files, data=data)
    assert r.status_code == 200, r.text
    doc_id = r.json()["document_id"]

    # List filtered
    lst = s.get(f"{BASE}/api/documents?linked_type=employee&linked_id={eid}").json()
    ids = [d["document_id"] for d in lst["items"]]
    assert doc_id in ids

    # Employee doc_ids updated
    prof = s.get(f"{BASE}/api/payroll/employees/{eid}").json()
    assert doc_id in (prof.get("document_ids") or [])

    # Delete (soft)
    d = s.delete(f"{BASE}/api/documents/{doc_id}")
    assert d.status_code in (200, 204)
    lst2 = s.get(f"{BASE}/api/documents?linked_type=employee&linked_id={eid}").json()
    ids2 = [x["document_id"] for x in lst2["items"]]
    assert doc_id not in ids2


# ---------- Regression: accounting endpoints ----------
@pytest.mark.parametrize("path", ["/api/dashboard", "/api/reports/pnl", "/api/gst", "/api/cogs"])
def test_regression_accounting(s, path):
    r = s.get(f"{BASE}{path}")
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
    assert isinstance(r.json(), (dict, list))
