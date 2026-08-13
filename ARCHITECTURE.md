# Urban Dotted Expense Book — System Design

## 1. System Architecture
- **Frontend**: React 19 (CRA/craco), react-router-dom 7, Tailwind + shadcn/ui, recharts, sonner. Light premium SaaS ("Old Money Tech" light theme).
- **Backend**: FastAPI, all routes under `/api`, modular routers (auth, categories, transactions, sales, refunds, inventory, cogs, assets, suppliers, accounts, recurring, reminders, month-end, gst, cashflow, documents, reports, export, import, search, demo, audit).
- **DB**: MongoDB (motor). Document model with explicit relational-style references + indexes. Every business-owned document carries `business_id` (tenant key) enforced server-side.
- **Money**: all amounts persisted as **integer cents** (`*_cents`). All computation via `decimal.Decimal` with `ROUND_HALF_UP`. No float arithmetic anywhere in the money path.
- **Files**: Emergent Object Storage; DB is source of truth (`documents` collection, soft delete). All downloads proxied through authenticated backend endpoint.
- **Locale**: AUD, `Australia/Adelaide`, `en-AU`, DD/MM/YYYY.

## 2. Database Schema (collections)
| Collection | Key fields |
|---|---|
| users | user_id, email, name, password_hash?, auth_provider, business_ids[], default_business_id, role |
| user_sessions | user_id, session_token, expires_at |
| login_attempts | identifier, count, locked_until |
| businesses | business_id, name, abn, gst_registered, default_gst_rate, timezone, currency, is_demo, owner_user_id |
| categories | category_id, business_id, name, parent_id (null=top), kind(expense/income), is_archived, sort |
| suppliers | supplier_id, business_id, name, country, abn, email, phone, website, notes, archived |
| payment_accounts | account_id, business_id, name, type, archived |
| products | product_id, business_id, sku, name, archived |
| transactions | txn_id, business_id, txn_type(expense/sale/refund/other_income), date, fy, month_key, category_id, subcategory_id, supplier_id, account_id, description, amount_ex_cents, gst_cents, amount_inc_cents, gst_treatment, gst_rate, reference, notes, tags[], recurring_template_id, receipt_document_ids[], needs_review, ask_accountant, accountant_note, reconcile_status, external_source, external_id, sale_fields{gross,discounts,shipping_revenue,tax_collected,fees,other_income,gift_cards}, refund_fields{reason,original_order,product_id}, items[{product_id,sku,qty}], ad_metrics{revenue,orders,clicks,impressions}, is_deleted, created_at/by, updated_at/by |
| inventory_purchases | purchase_id, business_id, supplier_id, date, fy, product_id, sku, qty, unit_cost_cents, freight_cents, customs_cents, import_gst_cents, other_cents, total_cost_cents, landed_unit_cost_cents, qty_sold, receipt_document_ids |
| cogs_entries | cogs_id, business_id, month_key, fy, source(auto/manual), product_id, qty, unit_cost_cents, amount_cents, txn_id? |
| assets | asset_id, business_id, name, date, supplier_id, invoice, price_ex_cents, gst_cents, price_inc_cents, serial, category_id, business_use_pct, status, notes, receipt_document_ids, needs_review |
| recurring_templates | template_id, business_id, name, category_id, subcategory_id, supplier_id, account_id, frequency, expected_amount_cents?, variable, gst_treatment, active, start_month |
| reminders | reminder_id, business_id, template_id?, category_id, month_key, kind(missing_recurring/detected_pattern), status(open/completed/skipped/snoozed/na), snooze_until |
| month_end_checks | business_id, month_key, items[{key,label,done}], custom_items |
| documents | document_id, business_id, storage_path, filename, content_type, size, linked_type, linked_id, fy, month_key, supplier_id, category_id, is_deleted |
| import_jobs | job_id, business_id, filename, mapping, rows_total, rows_imported, duplicates, created_at |
| audit_logs | log_id, business_id, user_id, entity, entity_id, action, before, after, at |
| integrations | business_id, provider, status(not_connected), config |

Indexes: `business_id` compound with `date`, `fy`, `month_key`, `category_id`; unique `(business_id, external_source, external_id)`; unique `users.email`; text-ish regex search on description/supplier.

## 3. Page / Screen Map
Login/Register → App shell (sidebar + FY selector + global search + Quick Add):
Dashboard, Sales, Refunds, Expenses (→ Category → Subcategory detail), Advertising, Inventory, COGS, Assets, Suppliers (→ Supplier detail), GST, Cash Flow, Transactions, Documents, Reports (16 reports), Month-End, Year-End, Accountant Export (wizard), Reminders, Settings (business, categories, accounts, products, demo data, backup).

## 4. Calculation Rules
```
Net Sales      = Gross Sales - Discounts - Refunds
Gross Profit   = Net Sales - COGS
Operating Profit = Gross Profit - Operating Expenses
Gross Margin % = Gross Profit / Net Sales
Refund Rate %  = Refunds / Gross Sales
Ad % of Net Sales = Advertising / Net Sales
Cash In/Out    = actual money movement (inc-GST amounts), separate from profit
```
All divisions guarded: `None` when denominator is 0 (never invented).

## 5. GST Handling Rules
| Treatment | ex | gst | inc |
|---|---|---|---|
| gst_included | inc/(1+r) | inc-ex | amount |
| gst_excluded | amount | ex*r | ex+gst |
| gst_free | amount | 0 | amount |
| no_gst | amount | 0 | amount |
| custom (rate + inclusive flag) | per flag | per rate | per flag |
| unknown | amount | 0 | amount, `needs_review=true` |
Default rate is a **business setting** (10%) but treatment is always per-transaction. Rounding ROUND_HALF_UP to cents. All GST/BAS output labelled "bookkeeping estimate — not a lodged BAS".

## 6. COGS Methodology
Inventory purchase → landed cost = (qty*unit_cost) + freight + customs + import GST(tracked separately for GST center) + other. `landed_unit_cost = landed_total / qty`.
COGS is **not** the purchase. COGS recognised when units sell: sale lines (`items[{sku,qty}]`) consume inventory at **weighted-average landed unit cost** across available purchases of that SKU (FIFO-ordered consumption of `qty_sold`). Manual COGS entries also supported for months without SKU-level data. COGS report shows the derivation per month.

## 7. Reminder Architecture
For each active recurring template and for each category with ≥3 months of history in the FY, the engine computes expected month keys and compares with actual transactions. Missing → `reminders` doc (idempotent on `business_id+key+month_key`). Statuses: open / completed / skipped / snoozed(until) / na. Recomputed on demand via `GET /api/reminders/scan`.

## 8. Shopify Integration Architecture (Phase 4 — not built)
`integrations` registry per business. Planned flow: OAuth install → webhooks (orders/create, orders/updated, refunds/create, payouts) → staging collection → mapper → `transactions` with `external_source="shopify"`, `external_id=gid`. Unique index gives idempotency. Sync never overwrites fields where `manually_reviewed=true` without explicit confirmation. Backfill via background reconciliation job. Currently exposed read-only as **"Coming in Phase 4"**.

## 9. Security Architecture
bcrypt hashing; JWT access(15m)+refresh(7d) httpOnly Secure SameSite=None cookies; Emergent Google Auth session tokens (7d, DB-backed); brute-force lockout (5 fails / 15 min); every query scoped by `business_id` after membership check; pydantic validation at boundary; file type + size validation (10MB, pdf/jpg/png/webp/csv); documents served only via authorised endpoint; audit log on all financial mutations; soft delete for financial records; no secrets in frontend.

## 10. Implementation Roadmap
- **Phase 1 (built)**: DB, auth (both), business settings, categories, transactions, expenses, sales, refunds, dashboard, AU FY, GST engine.
- **Phase 2 (built)**: receipts/documents, recurring, reminders, month-end, reports, PDF/CSV export, accountant export wizard.
- **Phase 3 (built)**: inventory, COGS, assets, suppliers, cash flow, reconciliation, CSV import.
- **Phase 4 (not built)**: Shopify sync — labelled in-app.
- **Phase 5 (not built)**: Ad platform APIs, bank feeds.
