import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtPct, fmtDate, errText } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, KpiCard, MonthBarChart, MonthLineChart,
  toChart, Pill, Disclaimer, StatRow,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { TxnTable, TxnDetail } from "@/pages/Transactions";
import { Plus, ArrowLeft } from "lucide-react";

export function Suppliers() {
  const { refreshKey, bump } = useApp();
  const [list, setList] = useState(null);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", country: "Australia", abn: "", email: "", phone: "", website: "", notes: "" });

  useEffect(() => {
    api.get("/suppliers").then(({ data }) => setList(data)).catch(() => setList(false));
  }, [refreshKey]);

  const save = async () => {
    try {
      await api.post("/suppliers", f);
      toast.success("Supplier created"); setOpen(false);
      setF({ name: "", country: "Australia", abn: "", email: "", phone: "", website: "", notes: "" });
      bump();
    } catch (e) { toast.error(errText(e)); }
  };

  if (!list) return <Loading label="Loading suppliers" />;

  return (
    <div data-testid="suppliers-page">
      <PageHeader title="Suppliers" subtitle="Supplier records with total spend, GST and monthly history.">
        <Button size="sm" className="rounded-sm gap-1.5 bg-primary text-primary-foreground"
          onClick={() => setOpen(true)} data-testid="add-supplier-btn"><Plus size={14} /> New supplier</Button>
      </PageHeader>

      <Section title={`${list.length} suppliers`} testId="suppliers-table">
        {list.length === 0 ? <Empty title="No suppliers yet" hint="Add one, or let CSV import create them automatically." /> : (
          <div className="divide-y divide-border">
            {list.map((s) => (
              <Link key={s.supplier_id} to={`/suppliers/${s.supplier_id}`} data-testid={`supplier-row-${s.supplier_id}`}
                className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-accent/40 transition-colors">
                <div>
                  <div className="text-sm font-semibold">{s.name}</div>
                  <div className="text-[11px] text-muted-foreground num">
                    {s.country}{s.abn ? ` · ABN ${s.abn}` : ""}{s.email ? ` · ${s.email}` : ""}
                  </div>
                </div>
                {s.is_demo && <Pill>Demo</Pill>}
              </Link>
            ))}
          </div>
        )}
      </Section>

      {open && (
        <Dialog open onOpenChange={() => setOpen(false)}>
          <DialogContent className="bg-popover rounded-sm" data-testid="supplier-dialog">
            <DialogHeader><DialogTitle className="font-serif text-xl">New supplier</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3">
              {[["name", "Supplier name"], ["country", "Country"], ["abn", "ABN (if relevant)"],
                ["email", "Email"], ["phone", "Phone"], ["website", "Website"]].map(([k, l]) => (
                <div key={k} className={k === "name" ? "col-span-2" : ""}>
                  <Label className="overline">{l}</Label>
                  <Input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}
                    className="rounded-sm" data-testid={`supplier-${k}`} />
                </div>
              ))}
              <div className="col-span-2">
                <Label className="overline">Notes</Label>
                <Input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} className="rounded-sm" data-testid="supplier-notes" />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">Cancel</Button>
              <Button onClick={save} disabled={!f.name.trim()} className="rounded-sm bg-primary text-primary-foreground"
                data-testid="supplier-save-btn">Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export function SupplierDetail() {
  const { supplierId } = useParams();
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);

  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/suppliers/${supplierId}/detail?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [supplierId, fy, refreshKey]);

  if (!d) return <Loading label="Loading supplier" />;
  if (d === false) return <Empty title="Supplier not found" />;

  return (
    <div data-testid="supplier-detail-page">
      <Link to="/suppliers" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-3" data-testid="back-to-suppliers">
        <ArrowLeft size={12} /> All suppliers
      </Link>
      <PageHeader title={d.supplier.name}
        subtitle={`${d.supplier.country}${d.supplier.abn ? ` · ABN ${d.supplier.abn}` : ""} · FY ${fy?.replace("FY", "")}`} />

      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-4">
        <KpiCard label="Total Spent" value={d.total_spent} testId="supplier-total" />
        <KpiCard label="GST Recorded" value={d.total_gst} testId="supplier-gst" />
        <KpiCard label="Transactions" value={String(d.transaction_count)} testId="supplier-txn-count" />
        <KpiCard label="Invoices" value={String(d.invoice_count)} testId="supplier-invoices" />
        <KpiCard label="Inventory Purchases" value={d.inventory_purchase_total} to="/inventory" testId="supplier-inventory" />
      </div>

      <Section title="Monthly history" testId="supplier-chart">
        <div className="p-3"><MonthBarChart data={toChart(d.monthly, (m) => ({ Spend: m.amount }))}
          keys={[{ key: "Spend", name: "Spend", color: "#0F291E" }]} /></div>
      </Section>

      {d.inventory_purchases.length > 0 && (
        <Section title="Inventory purchases" className="mt-4" testId="supplier-inventory-table">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "SKU", "Qty", "Total Cost"].map((h, i) => (
                  <TableHead key={h} className={`overline ${i > 1 ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {d.inventory_purchases.map((p) => (
                  <TableRow key={p.purchase_id}>
                    <TableCell className="num text-xs">{fmtDate(p.date)}</TableCell>
                    <TableCell className="num text-xs">{p.sku || "—"}</TableCell>
                    <TableCell className="text-right num text-xs">{p.qty}</TableCell>
                    <TableCell className="text-right"><Money value={p.total_cost} className="text-xs" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}

      <Section title={`Transactions (${d.transactions.length})`} className="mt-4" testId="supplier-transactions">
        {d.transactions.length === 0 ? <Empty title="No transactions for this supplier in this FY" />
          : <TxnTable items={d.transactions} onRowClick={setSel} />}
      </Section>
      {sel && <TxnDetail txn={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

export function GstCenter() {
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/gst?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);
  if (!d) return <Loading label="Loading GST centre" />;
  const t = d.totals;

  return (
    <div data-testid="gst-page">
      <PageHeader title="GST Centre"
        subtitle="GST is stored per transaction — 10% is a configurable default, never an assumption." />

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 border border-border bg-border mb-4">
        <KpiCard label="GST on Sales" value={t.gst_collected_on_sales} testId="gst-collected" />
        <KpiCard label="GST on Refunds" value={t.gst_on_refunds} tone="negative" testId="gst-refunds" />
        <KpiCard label="Net GST Collected" value={t.net_gst_collected} testId="gst-net-collected" />
        <KpiCard label="GST on Purchases" value={t.gst_recorded_on_purchases} testId="gst-purchases" />
        <KpiCard label="Import GST" value={t.import_gst} to="/inventory" testId="gst-import" />
        <KpiCard label="Est. GST Position" value={t.estimated_gst_position} tone="warning" testId="gst-position" />
      </div>

      <Disclaimer testId="gst-disclaimer">{d.disclaimer}</Disclaimer>

      <div className="grid gap-4 lg:grid-cols-2 mt-4">
        <Section title="Monthly GST" testId="gst-chart">
          <div className="p-3"><MonthBarChart data={toChart(d.months, (m) => ({
            Collected: m.gst_collected, "On purchases": m.gst_paid }))} keys={[
            { key: "Collected", name: "Collected", color: "#0F291E" },
            { key: "On purchases", name: "On purchases", color: "#2F5F73" }]} /></div>
        </Section>

        <Section title="By GST treatment" testId="gst-by-treatment"
          right={d.needs_review_count > 0 && <Pill tone="warning">{d.needs_review_count} need review</Pill>}>
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Treatment", "Count", "Amount", "GST"].map((h, i) => (
                <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {d.by_treatment.map((r) => (
                <TableRow key={r.treatment} data-testid={`gst-treatment-${r.treatment}`}>
                  <TableCell className="text-xs capitalize">{r.treatment.replace(/_/g, " ")}</TableCell>
                  <TableCell className="text-right num text-xs">{r.count}</TableCell>
                  <TableCell className="text-right"><Money value={r.amount} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={r.gst} className="text-xs" /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      </div>

      <Section title="BAS-ready quarterly view (estimates)" className="mt-4" testId="gst-quarters">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Quarter", "Sales (inc GST)", "GST Collected", "Purchases (inc GST)", "GST on Purchases", "Net GST"].map((h, i) => (
                <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {d.quarters.map((q) => (
                <TableRow key={q.quarter} data-testid={`gst-quarter-${q.quarter}`}>
                  <TableCell className="text-xs font-semibold">{q.quarter}</TableCell>
                  <TableCell className="text-right"><Money value={q.sales_inc} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={q.gst_collected} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={q.purchases_inc} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={q.gst_paid} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={q.net} className="text-xs font-semibold" /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="p-4 border-t border-border">
          <Button asChild variant="outline" size="sm" className="rounded-sm" data-testid="gst-report-link">
            <Link to="/reports/gst">Open GST report &amp; export</Link>
          </Button>
        </div>
      </Section>
    </div>
  );
}

export function CashFlow() {
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/cashflow?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);
  if (!d) return <Loading label="Loading cash flow" />;

  return (
    <div data-testid="cashflow-page">
      <PageHeader title="Cash Flow" subtitle="Actual money movement — deliberately different from accounting profit." />
      <div className="grid grid-cols-3 border border-border bg-border mb-4">
        <KpiCard label="Cash In" value={d.totals.cash_in} tone="positive" testId="cf-in" />
        <KpiCard label="Cash Out" value={d.totals.cash_out} tone="negative" testId="cf-out" />
        <KpiCard label="Net Cash Flow" value={d.totals.net_cash_flow}
          tone={d.totals.net_cash_flow >= 0 ? "positive" : "negative"} testId="cf-net" />
      </div>
      <Disclaimer testId="cf-note">{d.note}</Disclaimer>

      <Section title="Monthly cash flow" className="mt-4" testId="cf-chart">
        <div className="p-3"><MonthBarChart data={toChart(d.months, (m) => ({
          "Cash in": m.cash_in, "Cash out": m.cash_out }))} keys={[
          { key: "Cash in", name: "Cash in", color: "#166534" },
          { key: "Cash out", name: "Cash out", color: "#9F1239" }]} /></div>
      </Section>

      <Section title="Monthly table" className="mt-4" testId="cf-table">
        <Table>
          <TableHeader><TableRow className="hover:bg-transparent">
            {["Month", "Cash In", "Cash Out", "Net Cash Flow"].map((h, i) => (
              <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
          </TableRow></TableHeader>
          <TableBody>
            {d.months.map((m) => (
              <TableRow key={m.month_key} data-testid={`cf-month-${m.month_key}`}>
                <TableCell className="text-xs">{m.month_label}</TableCell>
                <TableCell className="text-right"><Money value={m.cash_in} className="text-xs" /></TableCell>
                <TableCell className="text-right"><Money value={m.cash_out} className="text-xs" /></TableCell>
                <TableCell className="text-right"><Money value={m.net_cash_flow} className="text-xs font-semibold" signed /></TableCell>
              </TableRow>
            ))}
            <TableRow className="bg-muted/40 font-semibold">
              <TableCell className="text-xs">FY Total</TableCell>
              <TableCell className="text-right"><Money value={d.totals.cash_in} className="text-xs font-semibold" /></TableCell>
              <TableCell className="text-right"><Money value={d.totals.cash_out} className="text-xs font-semibold" /></TableCell>
              <TableCell className="text-right"><Money value={d.totals.net_cash_flow} className="text-xs font-semibold" signed /></TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Section>
    </div>
  );
}
