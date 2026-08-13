import React, { useEffect, useState, useMemo, useCallback } from "react";
import { toast } from "sonner";
import { api, fmtMoney, fmtPct, fmtNum, errText, GST_LABELS, fmtDate } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Money, KpiCard, Pill, Disclaimer, StatRow } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useLookups } from "@/components/QuickAdd";
import {
  ChevronLeft, ChevronRight, Save, CheckCircle2, Settings2, Plus, Trash2,
  Upload, AlertTriangle, CalendarDays,
} from "lucide-react";

const NONE = "__none__";
const iso = (d) => d.toISOString().slice(0, 10);
const shift = (dateStr, days) => {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + days);
  return iso(d);
};
const STATUS_TONE = { complete: "positive", in_progress: "warning", closed: "neutral", not_started: "neutral" };
const STATUS_LABEL = { complete: "Complete", in_progress: "In progress", closed: "No business / closed", not_started: "Not started" };

export default function DailyEntry() {
  const { bump, fy } = useApp();
  const today = iso(new Date());
  const yesterday = shift(today, -1);
  const [entryDate, setEntryDate] = useState(yesterday);
  const [data, setData] = useState(null);
  const [vals, setVals] = useState({});
  const [saving, setSaving] = useState(false);
  const [customise, setCustomise] = useState(false);
  const [history, setHistory] = useState([]);
  const [periods, setPeriods] = useState(null);

  const load = useCallback(async (d) => {
    setData(null);
    try {
      const { data: e } = await api.get(`/daily/entry?entry_date=${d}`);
      setData(e);
      const v = {};
      e.fields.forEach((f) => {
        v[f.field_id] = {
          value: f.value ?? "", qty: f.qty ?? "", unit_cost: f.unit_cost ?? "",
          text: f.text ?? "", yesno: !!f.yesno, note: f.note || "", no_spend: !!f.no_spend,
        };
      });
      setVals(v);
    } catch (err) { toast.error(errText(err)); setData(false); }
  }, []);

  const loadAux = useCallback(() => {
    api.get(`/daily/history?fy=${fy}`).then(({ data }) => setHistory(data.rows)).catch(() => {});
    api.get(`/daily/periods?fy=${fy}`).then(({ data }) => setPeriods(data)).catch(() => {});
  }, [fy]);

  useEffect(() => { load(entryDate); }, [entryDate, load]);
  useEffect(() => { if (fy) loadAux(); }, [fy, loadAux]);

  const set = (fid, key) => (v) => setVals((p) => ({ ...p, [fid]: { ...p[fid], [key]: v } }));

  // live profit engine — recalculates on every keystroke, no save required
  const live = useMemo(() => {
    if (!data) return null;
    const amt = (f) => {
      const v = vals[f.field_id] || {};
      if (f.field_type === "calc_qty_unit") {
        if (v.qty === "" || v.qty === null) return null;
        const unit = v.unit_cost === "" || v.unit_cost === null ? (f.default_unit_cost || 0) : Number(v.unit_cost);
        return Number(v.qty || 0) * Number(unit || 0);
      }
      if (f.field_type === "text" || f.field_type === "yesno") return null;
      if (v.value === "" || v.value === null || v.value === undefined) return v.no_spend ? 0 : null;
      return Number(v.value);
    };
    const sum = (pred) => Math.round(data.fields.filter((f) => pred(f) && amt(f) !== null)
      .reduce((a, f) => a + amt(f), 0) * 100) / 100;
    const sales = sum((f) => f.role === "sales_total");
    const refunds = sum((f) => f.role === "refunds");
    const otherRev = sum((f) => f.role === "other_revenue");
    const ads = sum((f) => f.section === "advertising" && f.role === "expense");
    const courier = sum((f) => f.section === "courier");
    const cogs = sum((f) => f.section === "product_cogs" && f.role === "expense");
    const production = sum((f) => f.section === "production");
    const packaging = sum((f) => f.section === "packaging");
    const other = sum((f) => ["other", "custom"].includes(f.section) && f.role === "expense");
    const ordersField = data.fields.find((f) => f.role === "orders");
    const orders = ordersField ? Number(vals[ordersField.field_id]?.value || 0) : 0;
    const netSales = Math.round((sales - refunds + otherRev) * 100) / 100;
    const expenses = Math.round((ads + courier + cogs + production + packaging + other) * 100) / 100;
    const profit = Math.round((netSales - expenses) * 100) / 100;
    const missing = data.fields.filter((f) => f.requirement === "required" && amt(f) === null
      && !["text", "yesno"].includes(f.field_type)).map((f) => f.label);
    const subtotals = {};
    data.sections.forEach((s) => { subtotals[s.key] = sum((f) => f.section === s.key); });
    return { sales, orders, refunds, otherRev, netSales, ads, courier, cogs, production,
      packaging, other, expenses, profit, margin: netSales ? (profit / netSales) * 100 : null,
      missing, subtotals, amt };
  }, [data, vals]);

  const payload = (status) => ({
    entry_date: entryDate, status, notes: data?.notes || "",
    values: Object.fromEntries(Object.entries(vals).map(([fid, v]) => [fid, {
      value: v.value === "" ? null : Number(v.value),
      qty: v.qty === "" ? null : Number(v.qty),
      unit_cost: v.unit_cost === "" ? null : Number(v.unit_cost),
      text: v.text || null, yesno: v.yesno, note: v.note || "", no_spend: !!v.no_spend,
    }])),
  });

  const save = async (status) => {
    setSaving(true);
    try {
      const { data: e } = await api.post("/daily/entry", payload(status));
      setData(e);
      toast.success(status === "complete"
        ? `${e.date_label} marked complete — ${e.transactions_written} records fed into your reports`
        : "Draft saved");
      bump(); loadAux();
    } catch (err) { toast.error(errText(err)); loadAux(); } finally { setSaving(false); }
  };

  if (!data) return <Loading label="Loading daily entry" />;
  if (data === false) return <Empty title="Could not load daily entry" />;

  const isYesterdayPending = entryDate === yesterday && data.status !== "complete" && data.status !== "closed";

  return (
    <div data-testid="daily-entry-page">
      <PageHeader title="Daily Entry"
        subtitle="Enter one full day of trading from this single screen. Everything saved here flows straight into your dashboards, reports and accountant export — no re-entry anywhere.">
        <Button variant="outline" size="sm" className="rounded-sm gap-1.5" onClick={() => setCustomise(true)}
          data-testid="customise-daily-btn"><Settings2 size={14} /> Customise Daily Entry</Button>
      </PageHeader>

      {/* date navigation */}
      <Section testId="daily-date-nav">
        <div className="p-3 flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" className="rounded-sm gap-1" data-testid="prev-day-btn"
            onClick={() => setEntryDate(shift(entryDate, -1))}><ChevronLeft size={14} /> Previous day</Button>
          <Button variant={entryDate === yesterday ? "default" : "outline"} size="sm" className="rounded-sm"
            onClick={() => setEntryDate(yesterday)} data-testid="yesterday-btn">Yesterday</Button>
          <Button variant={entryDate === today ? "default" : "outline"} size="sm" className="rounded-sm"
            onClick={() => setEntryDate(today)} data-testid="today-btn">Today</Button>
          <Button variant="outline" size="sm" className="rounded-sm gap-1" data-testid="next-day-btn"
            onClick={() => setEntryDate(shift(entryDate, 1))}>Next day <ChevronRight size={14} /></Button>
          <Input type="date" value={entryDate} onChange={(e) => e.target.value && setEntryDate(e.target.value)}
            className="rounded-sm num w-[170px] h-9 ml-auto" data-testid="daily-date-input" />
          <Pill tone={STATUS_TONE[data.status]} testId="daily-status-pill">{STATUS_LABEL[data.status]}</Pill>
        </div>
        {isYesterdayPending && (
          <div className="px-4 py-2.5 border-t border-border bg-warning/5 flex items-center gap-2" data-testid="yesterday-waiting">
            <CalendarDays size={14} className="text-warning" />
            <span className="text-xs">Yesterday ({data.date_label}) is waiting to be completed.</span>
          </div>
        )}
      </Section>

      <div className="grid gap-4 mt-4 lg:grid-cols-[1fr_320px] items-start">
        {/* input sections */}
        <div className="space-y-4">
          {data.sections.map((s) => {
            const fields = data.fields.filter((f) => f.section === s.key);
            if (!fields.length) return null;
            return (
              <Section key={s.key} title={s.label} testId={`daily-section-${s.key}`}
                right={<span className="num text-xs font-semibold">{fmtMoney(live.subtotals[s.key] || 0)}</span>}>
                <div className="divide-y divide-border">
                  {fields.map((f) => (
                    <FieldRow key={f.field_id} f={f} v={vals[f.field_id] || {}} set={set}
                      amount={live.amt(f)} entryDate={entryDate} onUploaded={() => load(entryDate)} />
                  ))}
                </div>
              </Section>
            );
          })}

          <div className="grid-card p-4 flex flex-wrap gap-2 items-center" data-testid="daily-actions">
            <Button variant="outline" onClick={() => save("in_progress")} disabled={saving}
              className="rounded-sm gap-1.5" data-testid="save-draft-btn"><Save size={14} /> Save draft</Button>
            <Button onClick={() => save("complete")} disabled={saving || live.missing.length > 0}
              className="rounded-sm gap-1.5 bg-primary text-primary-foreground" data-testid="mark-complete-btn">
              <CheckCircle2 size={14} /> {saving ? "Saving…" : "Mark day complete"}
            </Button>
            <Button variant="outline" onClick={() => save("closed")} disabled={saving}
              className="rounded-sm text-xs" data-testid="mark-closed-btn">No business / closed</Button>
          </div>

          {live.missing.length > 0 && (
            <div className="grid-card p-4 border-l-2 border-l-warning" data-testid="missing-required">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle size={14} className="text-warning" />
                <span className="overline">Missing required fields</span>
              </div>
              <ul className="text-xs space-y-1 list-disc list-inside text-muted-foreground">
                {live.missing.map((m) => <li key={m}>{m}</li>)}
              </ul>
              <p className="text-[11px] text-muted-foreground mt-2">
                A blank field is not the same as $0. Tick “No spend” on a row to confirm there was genuinely no expense.
              </p>
            </div>
          )}
        </div>

        {/* sticky live summary */}
        <aside className="lg:sticky lg:top-[76px] space-y-4">
          <Section title="Live daily summary" testId="live-summary">
            <div className="p-4">
              <StatRow label="Sales" value={live.sales} />
              <StatRow label="Orders" value={fmtNum(live.orders)} />
              <StatRow label="less Refunds" value={-live.refunds} indent tone="negative" />
              {live.otherRev > 0 && <StatRow label="plus Other revenue" value={live.otherRev} indent />}
              <StatRow label="= Net Sales" value={live.netSales} bold />
              <StatRow label="Product / COGS" value={-live.cogs} indent tone="negative" />
              <StatRow label="Advertising" value={-live.ads} indent tone="negative" />
              <StatRow label="Courier" value={-live.courier} indent tone="negative" />
              <StatRow label="Production" value={-live.production} indent tone="negative" />
              <StatRow label="Packaging" value={-live.packaging} indent tone="negative" />
              <StatRow label="Other expenses" value={-live.other} indent tone="negative" />
              <StatRow label="= Estimated Profit" value={live.profit} bold
                tone={live.profit >= 0 ? "positive" : "negative"} formula="Net Sales − all daily costs" />
              <StatRow label="Profit Margin" value={live.margin === null ? "—" : `${live.margin.toFixed(2)}%`} bold />
            </div>
          </Section>
          {periods && (
            <Section title="Roll-up" testId="daily-periods">
              <div className="divide-y divide-border">
                {[["today", "Today"], ["week", "This week"], ["month", "This month"], ["fy", `FY ${fy?.replace("FY", "")}`]].map(([k, l]) => (
                  <div key={k} className="px-4 py-2.5 flex items-center justify-between" data-testid={`period-rollup-${k}`}>
                    <div>
                      <div className="text-xs font-semibold">{l}</div>
                      <div className="text-[10px] text-muted-foreground num">
                        {fmtMoney(periods[k].sales, 0)} sales · {periods[k].days_recorded} day(s)
                      </div>
                    </div>
                    <div className="text-right">
                      <Money value={periods[k].estimated_profit} decimals={0} className="text-sm font-semibold" />
                      <div className="text-[10px] text-muted-foreground num">{fmtPct(periods[k].profit_margin_pct)}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </aside>
      </div>

      {/* history */}
      <Section title={`Daily profit history — FY ${fy?.replace("FY", "")}`} className="mt-6" testId="daily-history">
        {!history.length ? <Empty title="No days recorded yet" hint="Save your first day above." /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "Sales", "Orders", "Refunds", "Ads", "COGS", "Courier", "Other", "Profit", "Margin", "Status"].map((h, i) => (
                  <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {history.map((r) => (
                  <TableRow key={r.date} className="cursor-pointer" data-testid={`history-row-${r.date}`}
                    onClick={() => setEntryDate(r.date)}>
                    <TableCell className="num text-xs whitespace-nowrap underline underline-offset-2 decoration-border">{r.date_label}</TableCell>
                    <TableCell className="text-right"><Money value={r.sales} className="text-xs" /></TableCell>
                    <TableCell className="text-right num text-xs">{r.orders}</TableCell>
                    <TableCell className="text-right"><Money value={r.refunds} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={r.advertising} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={r.cogs} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={r.courier} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={r.production + r.packaging + r.other_expenses} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={r.estimated_profit} className="text-xs font-semibold" signed /></TableCell>
                    <TableCell className="text-right num text-xs">{fmtPct(r.profit_margin_pct)}</TableCell>
                    <TableCell className="text-right"><Pill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</Pill></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <div className="p-4 border-t border-border">
          <Disclaimer>{periods?.note}</Disclaimer>
        </div>
      </Section>

      {customise && <Customise onClose={() => { setCustomise(false); load(entryDate); }} />}
    </div>
  );
}

function FieldRow({ f, v, set, amount, entryDate, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const upload = async (file) => {
    if (!file || !f.txn_id) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("linked_type", "transaction");
      fd.append("linked_id", f.txn_id);
      fd.append("doc_date", entryDate);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Receipt attached"); onUploaded();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="px-4 py-2 flex flex-wrap items-center gap-2" data-testid={`daily-field-${f.field_id}`}>
      <div className="w-[190px] shrink-0">
        <div className="text-xs font-medium flex items-center gap-1">
          {f.label}
          {f.requirement === "required" && <span className="text-warning">*</span>}
        </div>
        <div className="text-[10px] text-muted-foreground">
          {f.subcategory_name || f.category_name || "—"} · {GST_LABELS[f.gst_treatment]}
        </div>
      </div>

      {f.field_type === "calc_qty_unit" ? (
        <>
          <Input type="number" step="1" placeholder="Qty" value={v.qty ?? ""} onChange={(e) => set(f.field_id, "qty")(e.target.value)}
            className="rounded-sm num h-8 w-[90px]" data-testid={`qty-${f.field_id}`} />
          <span className="text-xs text-muted-foreground">×</span>
          <Input type="number" step="0.01" placeholder="Unit" value={v.unit_cost ?? ""} onChange={(e) => set(f.field_id, "unit_cost")(e.target.value)}
            className="rounded-sm num h-8 w-[90px]" data-testid={`unit-${f.field_id}`} />
          <span className="num text-xs font-semibold w-[80px] text-right" data-testid={`calc-${f.field_id}`}>
            {amount === null ? "—" : fmtMoney(amount)}
          </span>
        </>
      ) : f.field_type === "text" ? (
        <Input value={v.text ?? ""} onChange={(e) => set(f.field_id, "text")(e.target.value)}
          className="rounded-sm h-8 flex-1 min-w-[160px] text-xs" data-testid={`text-${f.field_id}`} />
      ) : f.field_type === "yesno" ? (
        <Switch checked={!!v.yesno} onCheckedChange={set(f.field_id, "yesno")} data-testid={`yesno-${f.field_id}`} />
      ) : (
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground">{f.field_type === "number" ? "#" : "$"}</span>
          <Input type="number" step={f.field_type === "number" ? "1" : "0.01"} placeholder="—"
            value={v.value ?? ""} onChange={(e) => set(f.field_id, "value")(e.target.value)}
            className="rounded-sm num h-8 w-[130px]" data-testid={`value-${f.field_id}`} />
        </div>
      )}

      {!["text", "yesno", "number"].includes(f.field_type) && (
        <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground cursor-pointer">
          <Switch checked={!!v.no_spend} onCheckedChange={set(f.field_id, "no_spend")}
            className="scale-75" data-testid={`nospend-${f.field_id}`} />
          No spend
        </label>
      )}

      <Input placeholder="Note" value={v.note ?? ""} onChange={(e) => set(f.field_id, "note")(e.target.value)}
        className="rounded-sm h-8 flex-1 min-w-[110px] text-xs" data-testid={`note-${f.field_id}`} />

      {f.txn_id && (
        <label className="cursor-pointer" title="Attach receipt" data-testid={`receipt-${f.field_id}`}>
          {f.receipt_document_ids?.length ? <Pill tone="positive">Receipt</Pill>
            : <Upload size={13} className={`text-muted-foreground hover:text-foreground ${busy ? "opacity-50" : ""}`} />}
          <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp"
            onChange={(e) => upload(e.target.files?.[0])} />
        </label>
      )}
    </div>
  );
}

function Customise({ onClose }) {
  const lk = useLookups();
  const [data, setData] = useState(null);
  const [f, setF] = useState({
    section: "custom", label: "", field_type: "currency", role: "expense", requirement: "optional",
    category_id: NONE, subcategory_id: NONE, gst_treatment: "gst_included", default_unit_cost: "", sku: "",
  });
  const load = () => api.get("/daily/fields").then(({ data }) => setData(data)).catch(() => setData(false));
  useEffect(() => { load(); }, []);

  const parents = lk.flat.filter((c) => !c.parent_id);
  const subs = lk.flat.filter((c) => c.parent_id === f.category_id);

  const add = async () => {
    try {
      await api.post("/daily/fields", {
        ...f, category_id: f.category_id === NONE ? null : f.category_id,
        subcategory_id: f.subcategory_id === NONE ? null : f.subcategory_id,
        default_unit_cost: f.default_unit_cost ? parseFloat(f.default_unit_cost) : null,
      });
      toast.success("Field added — it will appear every day from now on");
      setF({ ...f, label: "", default_unit_cost: "", sku: "" }); load();
    } catch (e) { toast.error(errText(e)); }
  };

  const patch = async (fld, changes) => {
    try {
      await api.put(`/daily/fields/${fld.field_id}`, {
        section: fld.section, label: fld.label, field_type: fld.field_type, role: fld.role,
        requirement: fld.requirement, category_id: fld.category_id, subcategory_id: fld.subcategory_id,
        gst_treatment: fld.gst_treatment, default_unit_cost: fld.default_unit_cost,
        sku: fld.sku, is_hidden: fld.is_hidden, ...changes,
      });
      load();
    } catch (e) { toast.error(errText(e)); }
  };

  const archive = async (id) => {
    try { await api.post(`/daily/fields/${id}/archive?archived=true`); toast.success("Field archived"); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="bg-popover max-w-5xl max-h-[92vh] overflow-y-auto rounded-sm" data-testid="customise-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">Customise Daily Entry</DialogTitle>
        </DialogHeader>
        {!data ? <Loading /> : (
          <>
            <p className="text-xs text-muted-foreground">
              Fields persist every day; amounts never carry over. Changing a default unit cost only affects
              future entries — historical records keep the cost that applied on their date.
            </p>

            <div className="overflow-x-auto border border-border">
              <Table>
                <TableHeader><TableRow className="hover:bg-transparent">
                  {["Field", "Section", "Type", "Category", "GST", "Unit cost", "Requirement", "Visible", ""].map((h, i) => (
                    <TableHead key={h + i} className="overline whitespace-nowrap">{h}</TableHead>))}
                </TableRow></TableHeader>
                <TableBody>
                  {data.fields.map((fld) => (
                    <TableRow key={fld.field_id} data-testid={`cust-row-${fld.field_id}`}>
                      <TableCell className="text-xs font-medium">{fld.label}</TableCell>
                      <TableCell className="text-xs capitalize">{fld.section.replace("_", " ")}</TableCell>
                      <TableCell className="text-xs num">{fld.field_type}</TableCell>
                      <TableCell className="text-xs">{fld.subcategory_name || fld.category_name || "—"}</TableCell>
                      <TableCell>
                        <Select value={fld.gst_treatment} onValueChange={(v) => patch(fld, { gst_treatment: v })}>
                          <SelectTrigger className="rounded-sm h-7 text-[11px] w-[140px]" data-testid={`cust-gst-${fld.field_id}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-popover">
                            {Object.entries(GST_LABELS).map(([k, l]) => <SelectItem key={k} value={k} className="text-xs">{l}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        {fld.field_type === "calc_qty_unit" ? (
                          <Input type="number" step="0.01" defaultValue={fld.default_unit_cost ?? ""}
                            onBlur={(e) => patch(fld, { default_unit_cost: e.target.value ? parseFloat(e.target.value) : null })}
                            className="rounded-sm num h-7 w-[80px] text-xs" data-testid={`cust-unit-${fld.field_id}`} />
                        ) : <span className="text-xs text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell>
                        <Select value={fld.requirement} onValueChange={(v) => patch(fld, { requirement: v })}>
                          <SelectTrigger className="rounded-sm h-7 text-[11px] w-[120px]" data-testid={`cust-req-${fld.field_id}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-popover">
                            {data.requirements.map((r) => <SelectItem key={r} value={r} className="text-xs capitalize">{r.replace("_", " ")}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell>
                        <Switch checked={!fld.is_hidden} onCheckedChange={(v) => patch(fld, { is_hidden: !v })}
                          className="scale-75" data-testid={`cust-visible-${fld.field_id}`} />
                      </TableCell>
                      <TableCell>
                        <button onClick={() => archive(fld.field_id)} className="text-muted-foreground hover:text-negative"
                          data-testid={`cust-archive-${fld.field_id}`}><Trash2 size={12} /></button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="border border-border p-3 grid gap-3 sm:grid-cols-3">
              <div className="sm:col-span-3 overline">Add a new field</div>
              <div><Label className="overline">Label</Label>
                <Input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })}
                  placeholder="e.g. DHL, Labels, Ink, Warehouse Supplies" className="rounded-sm h-8" data-testid="cust-new-label" /></div>
              <div><Label className="overline">Section</Label>
                <Select value={f.section} onValueChange={(v) => setF({ ...f, section: v })}>
                  <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-section"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {data.sections.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              <div><Label className="overline">Field type</Label>
                <Select value={f.field_type} onValueChange={(v) => setF({ ...f, field_type: v })}>
                  <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-type"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {data.field_types.map((t) => <SelectItem key={t} value={t} className="num text-xs">{t}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              <div><Label className="overline">Category</Label>
                <Select value={f.category_id} onValueChange={(v) => setF({ ...f, category_id: v, subcategory_id: NONE })}>
                  <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-category"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent className="bg-popover max-h-64">
                    <SelectItem value={NONE}>None</SelectItem>
                    {parents.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              {subs.length > 0 && (
                <div><Label className="overline">Subcategory</Label>
                  <Select value={f.subcategory_id} onValueChange={(v) => setF({ ...f, subcategory_id: v })}>
                    <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-subcategory"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent className="bg-popover max-h-64">
                      <SelectItem value={NONE}>None</SelectItem>
                      {subs.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select></div>
              )}
              <div><Label className="overline">GST treatment</Label>
                <Select value={f.gst_treatment} onValueChange={(v) => setF({ ...f, gst_treatment: v })}>
                  <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-gst"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {Object.entries(GST_LABELS).map(([k, l]) => <SelectItem key={k} value={k} className="text-xs">{l}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              <div><Label className="overline">Requirement</Label>
                <Select value={f.requirement} onValueChange={(v) => setF({ ...f, requirement: v })}>
                  <SelectTrigger className="rounded-sm h-8 text-xs" data-testid="cust-new-req"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {data.requirements.map((r) => <SelectItem key={r} value={r} className="text-xs capitalize">{r.replace("_", " ")}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              {f.field_type === "calc_qty_unit" && (
                <>
                  <div><Label className="overline">Default unit cost</Label>
                    <Input type="number" step="0.01" value={f.default_unit_cost}
                      onChange={(e) => setF({ ...f, default_unit_cost: e.target.value })}
                      className="rounded-sm num h-8" data-testid="cust-new-unit-cost" placeholder="1.00" /></div>
                  <div><Label className="overline">SKU (feeds COGS)</Label>
                    <Input value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })}
                      className="rounded-sm num h-8" data-testid="cust-new-sku" placeholder="CASE-IP17" /></div>
                </>
              )}
              <div className="flex items-end">
                <Button onClick={add} disabled={!f.label.trim()} className="rounded-sm bg-primary text-primary-foreground gap-1.5 h-8"
                  data-testid="cust-add-btn"><Plus size={13} /> Add field</Button>
              </div>
            </div>
          </>
        )}
        <DialogFooter>
          <Button onClick={onClose} className="rounded-sm bg-primary text-primary-foreground" data-testid="cust-close">Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
