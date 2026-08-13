# Urban Dotted Expense Book — PRD

## Original Problem Statement
Build a production-ready, modern, secure web application for an Australian eCommerce business
("urbandotted expense book"). It must act as a central financial record, expense tracker, revenue
tracker, GST tracker, inventory/COGS tracker, profitability dashboard, receipt/document manager and
accountant export system. Primary goal: *"Throughout the year I enter or import all business income
and expenses. At the end of the Australian financial year, I should be able to export clean,
organised records to PDF/CSV/Excel-compatible CSV and give them directly to my accountant or tax
agent."* Full 50-section spec supplied by the user covering flexible categories, GST per transaction,
COGS methodology, reminders, month/year-end close, accountant export, tax-safety wording and
phase-labelled future integrations.

## User Choices (as stated)
1. Auth: **both** custom JWT email/password **and** Emergent-managed Google login.
2. File storage: **Emergent object storage**.
3. Scope: **Phase 1 + 2 + 3** (incl. inventory, COGS, assets, suppliers, cash flow, reconciliation).
4. Demo data: **never auto-seeded**. Real businesses start empty; separate optional "Load Demo Data"
   (FY2025-26), clearly labelled, removable in one click without touching real data.
5. Design: **light premium SaaS**.

## Architecture
- **Frontend**: React 19, react-router-dom 7, Tailwind + shadcn/ui, recharts, sonner.
  Fonts: Cormorant Garamond (headings) / Manrope (body) / JetBrains Mono (all figures).
- **Backend**: FastAPI, modular routers all under `/api` — `auth.py`, `routes_setup.py`,
  `routes_txn.py`, `routes_inventory.py`, `routes_analytics.py`, `routes_ops.py`, `routes_reports.py`,
  shared `core.py` (money/GST/FY engine), `queries.py`, `seed.py`, `storage.py`.
- **DB**: MongoDB (motor). Every business-owned document carries `business_id`; tenancy enforced
  server-side in `get_business_id` (403 on foreign business). Indexes on business_id + date/fy/
  month_key/category_id, unique on (business_id, external_source, external_id) for import idempotency.
- **Money**: persisted as **integer cents**, all arithmetic `decimal.Decimal` + ROUND_HALF_UP. No floats.
- **Locale**: AUD, Australia/Adelaide, en-AU, DD/MM/YYYY, FY 1 July – 30 June.
- Full design docs (schema, calculation rules, GST rules, COGS methodology, reminder architecture,
  Shopify architecture, security architecture, roadmap) live in `/app/ARCHITECTURE.md`.

## User Personas
1. **Owner-operator (primary)** — runs the Shopify store, enters expenses monthly, wants zero
   surprises at 30 June and a single clean handover pack.
2. **Accountant / registered tax agent (consumer of output)** — receives the export pack, needs
   transparent derivations, flagged questions and clearly-labelled estimates.
3. **Future: bookkeeper / second business** — architecture is multi-business ready.

## Core Requirements (static)
- Unlimited categories + subcategories, user-managed (create/rename/archive). Nothing hard-coded.
- GST per transaction: included / excluded / GST-free / no GST / custom rate / unknown-needs-review.
  10% is a configurable business default, never an assumption.
- Australian FY everywhere with a selector; all historical years retained.
- COGS recognised when units **sell** (FIFO at landed unit cost), never at purchase.
- Every dashboard number drills down to its source transactions.
- Metrics are never invented — ROAS/CPA/CPC/CTR and % changes render "—" without valid inputs.
- Tax safety: no deductibility/depreciation/lodgement claims; "needs accountant review" available.
- Soft-delete/archive for all financial records; audit trail on financial mutations.
- Manual entry and CSV import must always remain available.

## Implemented (13 Aug 2026)
**Phase 1** — MongoDB schema + indexes; dual auth (bcrypt JWT access/refresh httpOnly cookies +
Emergent Google session exchange), brute-force lockout, password reset; business settings;
default category tree (17 categories / 31 subcategories) + 7 payment accounts seeded per new
business; transaction CRUD (expense/sale/refund/other income) with validation and duplicate
detection; Decimal GST engine (6 treatments); AU FY engine incl. BAS quarters; KPI dashboard
(12 clickable cards, 8 charts, attention widget, transparent profit breakdown); period switcher.

**Phase 2** — receipt/document vault on Emergent object storage (10MB + extension allowlist,
authenticated download proxy, soft delete); "Expenses Missing Receipts" report; recurring expense
templates (monthly/quarterly/annual/custom); smart missing-expense reminder engine (template-based
+ pattern detection, complete/skip/snooze/N-A, idempotent re-scan); month-end checklist with
auto-detection, custom items and completion %; year-end checklist with "Ready for Accountant"
gating and mark-reviewed overrides; 16 reports; CSV (UTF-8 BOM, spreadsheet-compatible) and PDF
(reportlab) export; 3-step Accountant Export wizard producing PDF / CSV / ZIP (PDF summary +
csv/ folder + receipts/ + manifest.json + README).

**Phase 3** — inventory purchases with landed cost (goods + freight + customs + import GST + other)
and landed unit cost; COGS engine with per-line derivation, inventory-on-hand valuation and
unmatched-unit detection, plus manual COGS entries; asset register (business-use %, serial, status,
accountant-review flag, no depreciation claims); suppliers + supplier detail (spend, GST, invoices,
inventory, monthly history); cash flow view; reconciliation statuses; CSV import with column mapping,
auto-detection and duplicate protection; global search (text/amount/month-name); rich filtering;
bulk actions; audit log viewer; JSON backup export; demo data load/purge.

**Phase-labelled in-app (not built, per spec)** — Shopify sync "Coming in Phase 4"; Meta/Google/
TikTok/Snapchat Ads, bank feeds, PayPal, Stripe, email reminders, JSON restore "Coming in Phase 5".

## Testing
- `/app/tests/test_calculations.py` — 25 unit tests: GST all treatments, decimal safety, no float
  drift, negative adjustments, FY boundaries (1 July / 30 June), BAS quarters, profit chain, landed
  unit cost, FIFO COGS, CSV parsers.
- `/app/backend/tests/test_api_comprehensive.py` — 47 API tests (auth, tenancy 401/403, dashboard,
  CRUD, reports, exports, documents, reminders, month/year-end).
- **72/72 passing.** Run: `cd /app && python -m pytest tests/ backend/tests/ -q`.
- Testing agent iteration 1: 0 critical, 0 UI bugs. Both reported minor items fixed (gst_rate now
  accepts percentage or fraction and rejects absurd values; login toast moved so it cannot overlay
  the FY selector). Additionally found and fixed reminder duplication after a demo reload.

## Prioritised Backlog
**P0 (next)**
- Shopify integration (Phase 4): OAuth install, webhooks (orders/refunds/payouts), staging + mapper,
  idempotent upsert, never overwrite manually-reviewed classifications without confirmation.
- Email delivery of missing-expense reminders (monthly digest).

**P1**
- Meta Ads / Google Ads spend + metrics sync (auto ROAS/CPA/CPC/CTR).
- Bank feed / PayPal / Stripe import and auto-matching for reconciliation.
- JSON backup restore/import.
- Multi-business switcher UI (backend already multi-tenant).
- This month vs same month last year comparison surfaced on the dashboard (`/api/compare` exists).

**P2**
- OCR receipt scanning to pre-fill expense fields.
- Budgets vs actuals per category.
- Product-level profitability.
- Depreciation schedule worksheet (still accountant-confirmed, never auto-claimed).
- Role-based access for a bookkeeper/accountant login.

## Next Tasks
1. Connect Shopify (needs store domain + API credentials from the user).
2. Turn on monthly email reminder digests.
3. Surface FY-vs-FY and month-vs-same-month-last-year comparisons on the dashboard.
4. Add budgets per category with variance alerts.
