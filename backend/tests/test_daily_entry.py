"""Daily Entry regression + integration tests.

Covers: template auto-seed, live totals math, blank-vs-zero, template
persistence with blank amounts next day, idempotency on re-save,
transaction removal when a field is blanked, default unit cost history
freeze, custom-field CRUD/archive, and one-source-of-truth propagation
into Advertising analytics + Transactions list.
"""
import os
import pytest
import requests
from datetime import date, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://expense-hub-au.preview.emergentagent.com").rstrip("/")
EMAIL = "admin@urbandotted.com.au"
PW = "UrbanDotted!2026"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PW})
    assert r.status_code == 200, r.text
    return sess


def _label_map(sess):
    r = sess.get(f"{BASE}/api/daily/fields")
    assert r.status_code == 200
    return {f["label"]: f for f in r.json()["fields"]}


def _pick_test_date(sess):
    """Pick a date that has no data (walk back from 2025-06-25).
    Uses FY2024-25 to avoid clashing with the FY2026-27 empty-check test
    running in parallel on another xdist worker."""
    d = date(2025, 6, 25)
    for _ in range(60):
        r = sess.get(f"{BASE}/api/daily/entry", params={"entry_date": d.isoformat()})
        assert r.status_code == 200
        blanks = all(f["is_blank"] for f in r.json()["fields"]
                     if f["field_type"] not in ("text", "yesno"))
        if blanks and r.json()["status"] == "not_started":
            return d
        d -= timedelta(days=1)
    raise RuntimeError("No clean day available")


@pytest.fixture(scope="module")
def test_date(s):
    d = _pick_test_date(s)
    yield d.isoformat()
    # cleanup
    s.delete(f"{BASE}/api/daily/entry/{d.isoformat()}")
    s.delete(f"{BASE}/api/daily/entry/{(d + timedelta(days=1)).isoformat()}")


class TestTemplate:
    def test_template_autoseed_has_default_fields(self, s):
        r = s.get(f"{BASE}/api/daily/fields")
        assert r.status_code == 200
        data = r.json()
        labels = {f["label"] for f in data["fields"]}
        # required core labels from PRD
        for req in ["Total Sales Received", "Total Orders", "Total Refunds",
                    "Meta / Facebook Ads", "Google Ads", "Snapchat Ads",
                    "Domestic Standard", "Mobile Covers Used",
                    "Sublimation Paper", "Printing Cost", "Electricity"]:
            assert req in labels, f"missing default field: {req}"
        assert len(data["fields"]) >= 18

    def test_sections_and_field_types_available(self, s):
        r = s.get(f"{BASE}/api/daily/fields").json()
        sect_keys = {sec["key"] for sec in r["sections"]}
        assert {"sales", "advertising", "courier", "product_cogs",
                "production", "packaging", "other", "custom"} <= sect_keys
        assert "calc_qty_unit" in r["field_types"]

    def test_mobile_covers_default_unit_cost_is_one(self, s):
        fm = _label_map(s)
        mc = fm["Mobile Covers Used"]
        assert mc["field_type"] == "calc_qty_unit"
        assert mc["default_unit_cost"] == 1.0


class TestUserExample:
    """Sales 700, Refunds 0 (no_spend), FB 70, Google 20, Snapchat 0 (no_spend),
       Dom Std 50, Mobile Covers qty 20 @ $1.00, Sub Paper 3, Printing 4."""

    def test_full_day_math(self, s, test_date):
        fm = _label_map(s)
        vals = {
            fm["Total Sales Received"]["field_id"]: {"value": 700},
            fm["Total Orders"]["field_id"]: {"value": 20},
            fm["Total Refunds"]["field_id"]: {"no_spend": True},
            fm["Meta / Facebook Ads"]["field_id"]: {"value": 70},
            fm["Google Ads"]["field_id"]: {"value": 20},
            fm["Snapchat Ads"]["field_id"]: {"no_spend": True},
            fm["Domestic Standard"]["field_id"]: {"value": 50},
            fm["Mobile Covers Used"]["field_id"]: {"qty": 20},
            fm["Sublimation Paper"]["field_id"]: {"value": 3},
            fm["Printing Cost"]["field_id"]: {"value": 4},
        }
        r = s.post(f"{BASE}/api/daily/entry",
                   json={"entry_date": test_date, "values": vals, "status": "in_progress"})
        assert r.status_code == 200, r.text
        t = r.json()["totals"]
        assert t["net_sales"] == 700
        assert t["orders"] == 20
        assert t["refunds"] == 0
        assert t["advertising"] == 90
        assert t["courier"] == 50
        assert t["cogs"] == 20         # 20 x $1.00 calc
        assert t["production"] == 7    # 3 + 4
        assert t["estimated_profit"] == 533
        assert abs(t["profit_margin_pct"] - 76.14) < 0.02

    def test_calc_qty_unit_row_shows_amount_20(self, s, test_date):
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": test_date}).json()
        mc = next(f for f in r["fields"] if f["label"] == "Mobile Covers Used")
        assert mc["qty"] == 20
        assert mc["unit_cost"] == 1.0
        assert mc["amount"] == 20.0
        assert mc["txn_id"] is not None

    def test_facebook_txn_written_and_gst_free(self, s, test_date):
        # Advertising analytics
        r = s.get(f"{BASE}/api/transactions",
                  params={"date_from": test_date, "date_to": test_date})
        assert r.status_code == 200
        rows = r.json().get("items", [])
        fb = [t for t in rows if "Facebook" in t.get("description", "")]
        assert len(fb) == 1
        assert fb[0]["amount_inc"] == 70.0
        assert fb[0]["gst"] == 0             # gst_free
        assert "daily-entry" in fb[0].get("tags", [])

    def test_google_ads_has_gst(self, s, test_date):
        r = s.get(f"{BASE}/api/transactions",
                  params={"date_from": test_date, "date_to": test_date}).json()
        rows = r.get("items", [])
        ga = [t for t in rows if "Google Ads" in t.get("description", "")]
        assert len(ga) == 1
        assert ga[0]["amount_inc"] == 20.0
        assert ga[0]["gst"] > 0

    def test_blank_vs_zero_snapchat_records_zero(self, s, test_date):
        # Snapchat had no_spend=True -> explicit $0 -> txn created with 0
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": test_date}).json()
        snap = next(f for f in r["fields"] if f["label"] == "Snapchat Ads")
        assert snap["no_spend"] is True
        # blank fields (like Meta/TikTok not set) should be_is_blank
        tiktok = next(f for f in r["fields"] if f["label"] == "TikTok Ads")
        assert tiktok["is_blank"] is True
        assert tiktok["amount"] is None


class TestIdempotencyAndBlanking:
    def test_resave_does_not_duplicate(self, s, test_date):
        r1 = s.get(f"{BASE}/api/transactions",
                   params={"date_from": test_date, "date_to": test_date}).json()
        count1 = len(r1.get("items", []))

        fm = _label_map(s)
        vals = {fm["Meta / Facebook Ads"]["field_id"]: {"value": 90}}
        r = s.post(f"{BASE}/api/daily/entry",
                   json={"entry_date": test_date, "values": vals, "status": "in_progress"})
        assert r.status_code == 200

        r2 = s.get(f"{BASE}/api/transactions",
                   params={"date_from": test_date, "date_to": test_date}).json()
        count2 = len(r2.get("items", []))
        assert count1 == count2

        rows = r2.get("items", [])
        fb = [t for t in rows if "Facebook" in t.get("description", "")]
        assert len(fb) == 1 and fb[0]["amount_inc"] == 90.0  # updated

    def test_blanking_removes_transaction(self, s, test_date):
        fm = _label_map(s)
        # Blank out Facebook (send no value + no_spend False)
        vals = {fm["Meta / Facebook Ads"]["field_id"]: {}}
        r = s.post(f"{BASE}/api/daily/entry",
                   json={"entry_date": test_date, "values": vals, "status": "in_progress"})
        assert r.status_code == 200
        rows = s.get(f"{BASE}/api/transactions",
                     params={"date_from": test_date, "date_to": test_date,
                             "search": "Facebook"}).json()
        rows = rows.get("items", [])
        assert not [t for t in rows if "Facebook" in t.get("description", "")]


class TestMarkComplete:
    def test_missing_required_refuses_complete(self, s, test_date):
        fm = _label_map(s)
        r = s.post(f"{BASE}/api/daily/entry",
                   json={"entry_date": test_date, "values": {}, "status": "complete"})
        assert r.status_code == 400
        assert "missing" in r.text.lower() or "Missing" in r.text


class TestNextDayPersistsFieldsButNotAmounts:
    def test_next_day_has_same_fields_blank_amounts(self, s, test_date):
        next_d = (date.fromisoformat(test_date) + timedelta(days=1)).isoformat()
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": next_d})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "not_started"
        labels_today = {f["label"] for f in
                        s.get(f"{BASE}/api/daily/entry",
                              params={"entry_date": test_date}).json()["fields"]}
        labels_next = {f["label"] for f in data["fields"]}
        assert labels_today == labels_next
        # every monetary field must be blank
        for f in data["fields"]:
            if f["field_type"] in ("currency", "calc_qty_unit"):
                assert f["amount"] is None
                assert f["value"] is None
                assert f["is_blank"] is True
        assert data["totals"]["estimated_profit"] == 0


class TestDefaultUnitCostHistoryFreeze:
    def test_change_default_does_not_alter_history(self, s, test_date):
        fm = _label_map(s)
        mc_id = fm["Mobile Covers Used"]["field_id"]

        # Confirm historical day has qty=20, unit=1, amount=20
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": test_date}).json()
        mc_before = next(f for f in r["fields"] if f["field_id"] == mc_id)
        assert mc_before["unit_cost"] == 1.0 and mc_before["amount"] == 20.0

        # Change default unit cost to 3.00
        put = s.put(f"{BASE}/api/daily/fields/{mc_id}",
                    json={"section": "product_cogs", "label": "Mobile Covers Used",
                          "field_type": "calc_qty_unit", "role": "expense",
                          "requirement": "required", "gst_treatment": "gst_included",
                          "default_unit_cost": 3.00})
        assert put.status_code == 200

        # Historical day untouched
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": test_date}).json()
        mc_hist = next(f for f in r["fields"] if f["field_id"] == mc_id)
        assert mc_hist["unit_cost"] == 1.0
        assert mc_hist["amount"] == 20.0

        # New (future) day prefills 3.00
        future = (date.fromisoformat(test_date) + timedelta(days=2)).isoformat()
        r = s.get(f"{BASE}/api/daily/entry", params={"entry_date": future}).json()
        mc_new = next(f for f in r["fields"] if f["field_id"] == mc_id)
        assert mc_new["unit_cost"] == 3.0 or mc_new["default_unit_cost"] == 3.0

        # restore
        s.put(f"{BASE}/api/daily/fields/{mc_id}",
              json={"section": "product_cogs", "label": "Mobile Covers Used",
                    "field_type": "calc_qty_unit", "role": "expense",
                    "requirement": "required", "gst_treatment": "gst_included",
                    "default_unit_cost": 1.00})


class TestCustomFieldsAndArchive:
    def test_create_visible_and_archive_custom_field(self, s):
        # create
        r = s.post(f"{BASE}/api/daily/fields",
                   json={"section": "courier", "label": "TEST_DHL Express",
                         "field_type": "currency", "role": "expense",
                         "requirement": "optional", "gst_treatment": "gst_free"})
        assert r.status_code == 200, r.text
        fid = r.json()["field_id"]

        # appears in listing
        labels = {f["label"] for f in s.get(f"{BASE}/api/daily/fields").json()["fields"]}
        assert "TEST_DHL Express" in labels

        # archive
        a = s.post(f"{BASE}/api/daily/fields/{fid}/archive", params={"archived": True})
        assert a.status_code == 200
        labels = {f["label"] for f in s.get(f"{BASE}/api/daily/fields").json()["fields"]}
        assert "TEST_DHL Express" not in labels


class TestHistoryAndPeriods:
    def test_history_row_present_for_test_date(self, s, test_date):
        r = s.get(f"{BASE}/api/daily/history", params={"limit": 30})
        assert r.status_code == 200
        rows = r.json()["rows"]
        row = next((x for x in rows if x["date"] == test_date), None)
        assert row is not None
        # sanity check some columns
        for k in ("sales", "advertising", "courier", "cogs",
                  "estimated_profit", "profit_margin_pct", "status"):
            assert k in row

    def test_periods_returns_all_windows(self, s):
        r = s.get(f"{BASE}/api/daily/periods")
        assert r.status_code == 200
        j = r.json()
        for k in ("today", "week", "month", "fy"):
            assert k in j
            assert "estimated_profit" in j[k]
            assert "days_recorded" in j[k]
