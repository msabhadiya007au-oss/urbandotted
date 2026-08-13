import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtDate, errText, monthLabel, fyMonthKeys, downloadFile } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, KpiCard, Pill, Disclaimer,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useLookups } from "@/components/QuickAdd";
import { Plus, Trash2, CheckCircle2, Database, Download, Upload, ArrowRight } from "lucide-react";

const NONE = "__none__";

export function MonthEnd() {
  const { fy, refreshKey, bump } = useApp();
  const [overview, setOverview] = useState(null);
  const [month, setMonth] = useState(null);
  const [detail, setDetail] = useState(null);
  const [yearEnd, setYearEnd] = useState(null);
  const [custom, setCustom] = useState("");

  const loadOverview = () => api.get(`/month-end?fy=${fy}`).then(({ data }) => {
    setOverview(data);
    setMonth((m) => m || data.months[0]?.month_key);
  }).catch(() => setOverview(false));
  const loadYearEnd = () => api.get(`/year-end?fy=${fy}`).then(({ data }) => setYearEnd(data)).catch(() => {});

  useEffect(() => { if (fy) { loadOverview(); loadYearEnd(); } }, [fy, refreshKey]); // eslint-disable-line
  useEffect(() => {
    if (!month) return;
    api.get(`/month-end/${month}`).then(({ data }) => setDetail(data)).catch(() => setDetail(false));
  }, [month, refreshKey]);

  const setItem = async (key, done) => {
    try {
      const { data } = await api.post(`/month-end/${month}/item`, { key, done });
      setDetail(data); loadOverview(); loadYearEnd();
    } catch (e) { toast.error(errText(e)); }
  };
  const addCustom = async () => {
    try {
      const { data } = await api.post(`/month-end/${month}/custom-item`, { label: custom });
      setDetail(data); setCustom(""); toast.success("Checklist item added");
    } catch (e) { toast.error(errText(e)); }
  };
  const close = async () => {
    try { await api.post(`/month-end/${month}/close?closed=${!detail.closed}`); loadOverview();
      setDetail({ ...detail, closed: !detail.closed }); toast.success("Month status updated"); }
    catch (e) { toast.error(errText(e)); }
  };
  const override = async (key) => {
    try { const { data } = await api.post(`/year-end/override?fy=${fy}`, { key, reviewed: true });
      setYearEnd(data); toast.success("Marked as reviewed"); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!overview) return <Loading label="Loading month-end" />;

  return (
    <div data-testid="month-end-page">
      <PageHeader title="Month-End &amp; Year-End Close"
        subtitle="Work through each month, then confirm the year is ready for your accountant." />

      <Section title={`Month completion — FY ${fy?.replace("FY", "")}`} testId="month-overview">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-border">
          {overview.months.map((m) => (
            <button key={m.month_key} onClick={() => setMonth(m.month_key)} data-testid={`month-tile-${m.month_key}`}
              className={`bg-card p-3 text-left transition-colors ${month === m.month_key ? "bg-accent/60" : "hover:bg-accent/30"}`}>
              <div className="text-xs font-semibold">{m.month_label}</div>
              <div className="num text-lg mt-1">{m.completion_pct}%</div>
              <Progress value={m.completion_pct} className="h-1 rounded-none mt-1.5" />
              {m.closed && <Pill tone="positive">Closed</Pill>}
            </button>
          ))}
        </div>
      </Section>

      {detail && (
        <Section className="mt-4" testId="month-detail"
          title={`${detail.month_label} checklist — ${detail.completion_pct}% complete`}
          right={<Button size="sm" variant={detail.closed ? "default" : "outline"} className="rounded-sm text-xs"
            onClick={close} data-testid="close-month-btn">{detail.closed ? "Reopen month" : "Mark month closed"}</Button>}>
          <div className="divide-y divide-border">
            {detail.items.map((it) => (
              <label key={it.key} className="flex items-center gap-3 px-4 py-2.5 cursor-pointer hover:bg-accent/20" data-testid={`check-${it.key}`}>
                <Checkbox checked={it.done} onCheckedChange={(v) => setItem(it.key, !!v)} />
                <span className={`text-sm flex-1 ${it.done ? "text-muted-foreground line-through" : ""}`}>{it.label}</span>
                {it.auto_detected && !it.manually_set && <Pill tone="positive">Auto-detected</Pill>}
                {it.custom && <Pill>Custom</Pill>}
              </label>
            ))}
          </div>
          <div className="p-4 border-t border-border flex gap-2">
            <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Add a custom checklist item"
              className="rounded-sm max-w-sm text-sm" data-testid="custom-item-input" />
            <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={addCustom} disabled={!custom.trim()}
              data-testid="custom-item-add"><Plus size={13} /> Add</Button>
          </div>
        </Section>
      )}

      {yearEnd && (
        <Section className="mt-6" testId="year-end-section"
          title={`Year-end checklist — FY ${fy?.replace("FY", "")}`}
          right={<Pill tone={yearEnd.ready_for_accountant ? "positive" : "warning"} testId="ready-for-accountant">
            {yearEnd.ready_for_accountant ? "Ready for Accountant" : `${yearEnd.completion_pct}% resolved`}
          </Pill>}>
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Check", "Mandatory", "Value", "Status", ""].map((h, i) => (
                <TableHead key={h + i} className={`overline ${i > 1 ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {yearEnd.checks.map((c) => (
                <TableRow key={c.key} data-testid={`year-end-${c.key}`}>
                  <TableCell className="text-xs">{c.label}</TableCell>
                  <TableCell className="text-xs">{c.mandatory ? "Yes" : "No"}</TableCell>
                  <TableCell className="text-right num text-xs">{String(c.value)}</TableCell>
                  <TableCell className="text-right">
                    <Pill tone={c.ok ? "positive" : "warning"}>
                      {c.resolved ? "Resolved" : c.marked_reviewed ? "Marked reviewed" : "Outstanding"}
                    </Pill>
                  </TableCell>
                  <TableCell className="text-right">
                    {!c.ok && (
                      <Button size="sm" variant="outline" className="rounded-sm h-6 text-[10px]"
                        onClick={() => override(c.key)} data-testid={`year-end-review-${c.key}`}>Mark reviewed</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="p-4 border-t border-border">
            <Button asChild size="sm" className="rounded-sm bg-primary text-primary-foreground gap-1.5" data-testid="go-to-export">
              <Link to="/accountant-export">Go to Accountant Export <ArrowRight size={13} /></Link>
            </Button>
          </div>
        </Section>
      )}
    </div>
  );
}

export function SearchResults() {
  const [sp] = useSearchParams();
  const q = sp.get("q") || "";
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!q) return; setD(null);
    api.get(`/search?q=${encodeURIComponent(q)}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [q]);
  if (!q) return <Empty title="Enter a search term" />;
  if (!d) return <Loading label="Searching" />;

  const groups = [
    ["Transactions", d.transactions, (t) => ({ key: t.txn_id, main: t.description || t.category_name,
      sub: `${fmtDate(t.date)} · ${t.supplier_name || "—"} · ${fmtMoney(t.amount_inc)}`,
      to: t.category_id ? `/expenses/${t.subcategory_id || t.category_id}` : "/transactions" })],
    ["Suppliers", d.suppliers, (s) => ({ key: s.supplier_id, main: s.name, sub: s.country, to: `/suppliers/${s.supplier_id}` })],
    ["Categories", d.categories, (c) => ({ key: c.category_id, main: c.name, sub: c.kind, to: `/expenses/${c.category_id}` })],
    ["Products", d.products, (p) => ({ key: p.product_id, main: `${p.sku} — ${p.name}`, sub: "Product", to: "/inventory" })],
    ["Assets", d.assets, (a) => ({ key: a.asset_id, main: a.name, sub: `${fmtDate(a.date)} · ${fmtMoney(a.price_inc)}`, to: "/assets" })],
    ["Inventory purchases", d.inventory_purchases, (p) => ({ key: p.purchase_id, main: `${p.sku || "—"} · ${p.description || ""}`,
      sub: `${fmtDate(p.date)} · ${fmtMoney(p.total_cost)}`, to: "/inventory" })],
    ["Documents", d.documents, (doc) => ({ key: doc.document_id, main: doc.filename, sub: fmtDate(doc.date), to: "/documents" })],
  ];

  return (
    <div data-testid="search-page">
      <PageHeader title={`Search: “${q}”`} subtitle={`${d.total_results} results across transactions, suppliers, categories, products, assets, inventory and documents.`} />
      <div className="space-y-4">
        {groups.filter(([, items]) => items?.length).map(([title, items, map]) => (
          <Section key={title} title={`${title} (${items.length})`} testId={`search-group-${title}`}>
            <div className="divide-y divide-border">
              {items.map((it) => {
                const r = map(it);
                return (
                  <Link key={r.key} to={r.to} data-testid={`search-result-${r.key}`}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-accent/40 transition-colors">
                    <div>
                      <div className="text-sm">{r.main}</div>
                      <div className="text-[11px] text-muted-foreground num">{r.sub}</div>
                    </div>
                    <ArrowRight size={13} className="opacity-30" />
                  </Link>
                );
              })}
            </div>
          </Section>
        ))}
        {d.total_results === 0 && <Empty title="No matches" hint="Try a supplier name, an amount like $120, or a month like January 2026." />}
      </div>
    </div>
  );
}

export function ImportCsv() {
  const { bump } = useApp();
  const lk = useLookups();
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [txnType, setTxnType] = useState("expense");
  const [gst, setGst] = useState("gst_included");
  const [defaultCat, setDefaultCat] = useState(NONE);
  const [fields, setFields] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get("/import/fields").then(({ data }) => setFields(data.system_fields)).catch(() => {}); }, []);

  const choose = async (file) => {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/import/preview", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(data);
      const auto = {};
      data.headers.forEach((h) => {
        const l = h.toLowerCase();
        if (/date/.test(l)) auto.date = h;
        else if (/(debit|amount|total|spend)/.test(l)) auto.amount = h;
        else if (/(merchant|supplier|vendor|payee)/.test(l)) auto.supplier = h;
        else if (/(description|narrative|memo|detail)/.test(l)) auto.description = h;
        else if (/(reference|invoice)/.test(l)) auto.reference = h;
        else if (/(category)/.test(l)) auto.category = h;
        else if (/(order|external|id)/.test(l)) auto.external_id = h;
      });
      setMapping(auto);
      setResult(null);
    } catch (e) { toast.error(errText(e)); }
  };

  const commit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/import/commit", {
        filename: preview.filename, raw: preview.raw, mapping, txn_type: txnType,
        gst_treatment: gst, default_category_id: defaultCat === NONE ? null : defaultCat, source: "csv",
      });
      setResult(data);
      toast.success(`${data.rows_imported} imported · ${data.duplicates} duplicates skipped`);
      bump();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div data-testid="import-page">
      <PageHeader title="CSV Import" subtitle="Map your CSV columns to system fields. Duplicate detection runs on every row.">
        <Label className="cursor-pointer inline-flex items-center gap-1.5 border border-border px-3 h-9 rounded-sm text-xs hover:bg-accent" data-testid="import-choose-file">
          <Upload size={14} /> Choose CSV
          <input type="file" accept=".csv" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
        </Label>
      </PageHeader>

      {!preview ? (
        <Empty title="No file selected" hint="Supports Shopify exports, bank transaction CSVs, advertising exports and any custom CSV." />
      ) : (
        <>
          <Section title={`${preview.filename} — ${preview.row_count} rows`} testId="import-mapping">
            <div className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {fields.map((f) => (
                <div key={f.key}>
                  <Label className="overline">{f.label}{f.required ? " *" : ""}</Label>
                  <Select value={mapping[f.key] || NONE} onValueChange={(v) => setMapping({ ...mapping, [f.key]: v === NONE ? undefined : v })}>
                    <SelectTrigger className="rounded-sm text-xs" data-testid={`map-${f.key}`}><SelectValue placeholder="Not mapped" /></SelectTrigger>
                    <SelectContent className="bg-popover max-h-72">
                      <SelectItem value={NONE}>Not mapped</SelectItem>
                      {preview.headers.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              ))}
              <div>
                <Label className="overline">Import as</Label>
                <Select value={txnType} onValueChange={setTxnType}>
                  <SelectTrigger className="rounded-sm text-xs" data-testid="import-txn-type"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {["expense", "sale", "refund", "other_income"].map((t) => (
                      <SelectItem key={t} value={t} className="capitalize">{t.replace("_", " ")}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="overline">GST treatment</Label>
                <Select value={gst} onValueChange={setGst}>
                  <SelectTrigger className="rounded-sm text-xs" data-testid="import-gst"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {["gst_included", "gst_excluded", "gst_free", "no_gst", "unknown"].map((t) => (
                      <SelectItem key={t} value={t}>{t.replace(/_/g, " ")}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="overline">Fallback category</Label>
                <Select value={defaultCat} onValueChange={setDefaultCat}>
                  <SelectTrigger className="rounded-sm text-xs" data-testid="import-default-category"><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent className="bg-popover max-h-72">
                    <SelectItem value={NONE}>None (leave uncategorised)</SelectItem>
                    {lk.flat.filter((c) => !c.parent_id).map((c) => (
                      <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="p-4 border-t border-border">
              <Button onClick={commit} disabled={busy || !mapping.date || !mapping.amount} data-testid="import-commit-btn"
                className="rounded-sm bg-primary text-primary-foreground">
                {busy ? "Importing…" : "Import rows"}
              </Button>
              {(!mapping.date || !mapping.amount) && <p className="text-[11px] text-warning mt-2">Map Date and Amount to continue.</p>}
            </div>
          </Section>

          <Section title="Sample rows" className="mt-4" testId="import-preview">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow className="hover:bg-transparent">
                  {preview.headers.map((h) => <TableHead key={h} className="overline whitespace-nowrap">{h}</TableHead>)}
                </TableRow></TableHeader>
                <TableBody>
                  {preview.sample_rows.map((row, i) => (
                    <TableRow key={i}>{row.map((c, j) => <TableCell key={j} className="text-xs num">{c}</TableCell>)}</TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Section>
        </>
      )}

      {result && (
        <Section title="Import result" className="mt-4" testId="import-result">
          <div className="p-4 grid grid-cols-3 gap-4">
            <div><div className="overline">Imported</div><div className="num text-2xl text-positive">{result.rows_imported}</div></div>
            <div><div className="overline">Duplicates skipped</div><div className="num text-2xl text-warning">{result.duplicates}</div></div>
            <div><div className="overline">Rows skipped</div><div className="num text-2xl text-muted-foreground">{result.skipped}</div></div>
          </div>
          {result.errors?.length > 0 && (
            <ul className="px-4 pb-4 space-y-1 text-[11px] text-muted-foreground list-disc list-inside">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </Section>
      )}
    </div>
  );
}
