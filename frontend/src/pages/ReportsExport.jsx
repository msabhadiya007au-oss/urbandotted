import React, { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtDate, errText, downloadFile, monthLabel, fyMonthKeys } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, KpiCard, Pill, Disclaimer,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import QuickAdd from "@/components/QuickAdd";
import { Download, FileText, ArrowLeft, Upload, Trash2, Plus, CheckCircle2, Clock, XCircle, BellOff } from "lucide-react";

export function Reports() {
  const { fy } = useApp();
  const [list, setList] = useState(null);
  useEffect(() => { api.get("/reports").then(({ data }) => setList(data)).catch(() => setList(false)); }, []);
  if (!list) return <Loading label="Loading reports" />;

  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports" subtitle={`All reports respect the selected financial year (${fy?.replace("FY", "")}) and export to PDF or CSV.`}>
        <Button asChild size="sm" className="rounded-sm bg-primary text-primary-foreground" data-testid="reports-export-link">
          <Link to="/accountant-export">Accountant export wizard</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-px sm:grid-cols-2 lg:grid-cols-3 bg-border border border-border">
        {list.reports.map((r) => (
          <div key={r.key} className="bg-card p-4 flex flex-col gap-3" data-testid={`report-card-${r.key}`}>
            <div>
              <div className="font-serif text-lg">{r.label}</div>
              <div className="overline mt-1">{fy?.replace("FY", "FY ")}</div>
            </div>
            <div className="flex gap-2 mt-auto">
              <Button asChild size="sm" variant="outline" className="rounded-sm text-xs" data-testid={`report-view-${r.key}`}>
                <Link to={`/reports/${r.key}`}>View</Link>
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1" data-testid={`report-csv-${r.key}`}
                onClick={() => downloadFile(`/reports/${r.key}/csv?fy=${fy}`, `${r.key}_${fy}.csv`)}>
                <Download size={12} /> CSV
              </Button>
              <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1" data-testid={`report-pdf-${r.key}`}
                onClick={() => downloadFile(`/reports/${r.key}/pdf?fy=${fy}`, `${r.key}_${fy}.pdf`)}>
                <FileText size={12} /> PDF
              </Button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-6"><Disclaimer>{list.disclaimer}</Disclaimer></div>
    </div>
  );
}

export function ReportView() {
  const { reportKey } = useParams();
  const { fy } = useApp();
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/reports/${reportKey}?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [reportKey, fy]);
  if (!d) return <Loading label="Building report" />;
  if (d === false) return <Empty title="Report not found" />;

  const isNum = (v) => typeof v === "number";

  return (
    <div data-testid="report-view-page">
      <Link to="/reports" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-3" data-testid="back-to-reports">
        <ArrowLeft size={12} /> All reports
      </Link>
      <PageHeader title={d.title} subtitle={`Financial year ${fy?.replace("FY", "")}`}>
        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" data-testid="report-download-csv"
          onClick={() => downloadFile(`/reports/${reportKey}/csv?fy=${fy}`, `${reportKey}_${fy}.csv`)}>
          <Download size={14} /> CSV
        </Button>
        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" data-testid="report-download-pdf"
          onClick={() => downloadFile(`/reports/${reportKey}/pdf?fy=${fy}`, `${reportKey}_${fy}.pdf`)}>
          <FileText size={14} /> PDF
        </Button>
      </PageHeader>

      <Section title={`${d.rows.length} rows`} testId="report-table">
        {d.rows.length === 0 ? <Empty title="No records for this financial year" /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {d.columns.map((c, i) => (
                  <TableHead key={c} className={`overline whitespace-nowrap ${i ? "text-right" : ""}`}>{c}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {d.rows.map((row, ri) => (
                  <TableRow key={ri} data-testid={`report-row-${ri}`}
                    className={String(row[0]).includes("TOTAL") ? "bg-muted/40 font-semibold" : ""}>
                    {row.map((cell, ci) => (
                      <TableCell key={ci} className={`text-xs ${ci ? "text-right num" : ""}`}>
                        {isNum(cell) ? fmtMoney(cell) : String(cell ?? "—")}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {d.notes?.length > 0 && (
          <div className="p-4 border-t border-border space-y-1.5">
            {d.notes.map((n, i) => <p key={i} className="text-[11px] text-muted-foreground">{n}</p>)}
          </div>
        )}
      </Section>
      <div className="mt-4"><Disclaimer>{d.disclaimer}</Disclaimer></div>
    </div>
  );
}

export function AccountantExport() {
  const { fy, meta } = useApp();
  const [step, setStep] = useState(1);
  const [selFy, setSelFy] = useState(fy);
  const [reports, setReports] = useState([]);
  const [all, setAll] = useState([]);
  const [format, setFormat] = useState("zip");
  const [receipts, setReceipts] = useState(true);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(null);

  useEffect(() => { api.get("/reports").then(({ data }) => { setAll(data.reports); setReports(data.reports.map((r) => r.key)); }); }, []);
  useEffect(() => { if (selFy) api.get(`/year-end?fy=${selFy}`).then(({ data }) => setReady(data)).catch(() => {}); }, [selFy]);
  useEffect(() => setSelFy(fy), [fy]);

  const toggle = (k) => setReports((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));

  const run = async () => {
    setBusy(true);
    try {
      const ext = format === "zip" ? "zip" : format;
      await downloadFile("/export/accountant", `accountant_pack_${selFy}.${ext}`, {
        method: "POST", data: { fy: selFy, reports, format, include_receipts: receipts },
      });
      toast.success("Export downloaded");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const STEPS = ["Financial year", "Select reports", "Format & download"];

  return (
    <div data-testid="accountant-export-page">
      <PageHeader title="Accountant Export"
        subtitle="Three steps to a clean pack you can hand straight to your accountant or registered tax agent." />

      <div className="grid grid-cols-3 border border-border bg-border mb-6">
        {STEPS.map((s, i) => (
          <button key={s} onClick={() => setStep(i + 1)} data-testid={`export-step-${i + 1}`}
            className={`bg-card p-4 text-left border border-border transition-colors ${step === i + 1 ? "bg-accent/60" : "hover:bg-accent/30"}`}>
            <div className="overline">Step {i + 1}</div>
            <div className="font-serif text-lg mt-1">{s}</div>
          </button>
        ))}
      </div>

      {step === 1 && (
        <Section title="Choose the financial year" testId="export-step1">
          <div className="p-4 space-y-4 max-w-md">
            <Select value={selFy} onValueChange={setSelFy}>
              <SelectTrigger className="rounded-sm num" data-testid="export-fy-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">
                {(meta?.fy_options || []).map((f) => <SelectItem key={f} value={f} className="num">{f.replace("FY", "FY ")}</SelectItem>)}
              </SelectContent>
            </Select>
            {ready && (
              <div className="border border-border p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="overline">Year-end readiness</span>
                  <Pill tone={ready.ready_for_accountant ? "positive" : "warning"} testId="export-ready-pill">
                    {ready.ready_for_accountant ? "Ready for Accountant" : "Checks outstanding"}
                  </Pill>
                </div>
                <Progress value={ready.completion_pct} className="h-1.5 rounded-none" />
                <p className="text-[11px] text-muted-foreground mt-2 num">{ready.completion_pct}% of checks resolved</p>
                <Button asChild size="sm" variant="outline" className="rounded-sm mt-3 text-xs" data-testid="export-year-end-link">
                  <Link to="/month-end">Open year-end checklist</Link>
                </Button>
              </div>
            )}
            <Button onClick={() => setStep(2)} className="rounded-sm bg-primary text-primary-foreground" data-testid="export-next-1">Next: reports</Button>
          </div>
        </Section>
      )}

      {step === 2 && (
        <Section title={`Select reports (${reports.length} of ${all.length})`} testId="export-step2"
          right={<button onClick={() => setReports(reports.length === all.length ? [] : all.map((r) => r.key))}
            className="text-[11px] underline underline-offset-2" data-testid="export-toggle-all">
            {reports.length === all.length ? "Clear all" : "Select all"}
          </button>}>
          <div className="p-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {all.map((r) => (
              <label key={r.key} className="flex items-center gap-2 text-sm cursor-pointer border border-border px-3 py-2 hover:bg-accent/30">
                <Checkbox checked={reports.includes(r.key)} onCheckedChange={() => toggle(r.key)} data-testid={`export-report-${r.key}`} />
                {r.label}
              </label>
            ))}
          </div>
          <div className="p-4 border-t border-border flex gap-2">
            <Button variant="outline" onClick={() => setStep(1)} className="rounded-sm">Back</Button>
            <Button onClick={() => setStep(3)} disabled={!reports.length} data-testid="export-next-2"
              className="rounded-sm bg-primary text-primary-foreground">Next: format</Button>
          </div>
        </Section>
      )}

      {step === 3 && (
        <Section title="Choose format and download" testId="export-step3">
          <div className="p-4 space-y-4 max-w-lg">
            <div className="grid grid-cols-3 gap-2">
              {[["pdf", "PDF", "Professional summary document"],
                ["csv", "CSV", "Spreadsheet compatible"],
                ["zip", "ZIP bundle", "PDF + CSVs + receipts"]].map(([k, l, h]) => (
                <button key={k} onClick={() => setFormat(k)} data-testid={`export-format-${k}`}
                  className={`text-left border p-3 transition-colors ${format === k ? "border-primary bg-accent/50" : "border-border hover:bg-accent/30"}`}>
                  <div className="font-serif text-base">{l}</div>
                  <div className="text-[10px] text-muted-foreground mt-1">{h}</div>
                </button>
              ))}
            </div>
            {format === "zip" && (
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <Checkbox checked={receipts} onCheckedChange={(v) => setReceipts(!!v)} data-testid="export-include-receipts" />
                Include receipt and invoice files
              </label>
            )}
            <div className="border border-border p-3 text-xs space-y-1">
              <div className="overline mb-1">Summary</div>
              <p className="num">Financial year: {selFy?.replace("FY", "FY ")}</p>
              <p className="num">Reports: {reports.length}</p>
              <p className="num">Format: {format.toUpperCase()}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setStep(2)} className="rounded-sm">Back</Button>
              <Button onClick={run} disabled={busy} data-testid="export-download-btn"
                className="rounded-sm bg-primary text-primary-foreground gap-1.5">
                <Download size={14} /> {busy ? "Generating…" : "Generate & download"}
              </Button>
            </div>
            <Disclaimer>Nothing is lodged with the ATO. This pack is bookkeeping records for review.</Disclaimer>
          </div>
        </Section>
      )}
    </div>
  );
}

export function Documents() {
  const { fy, refreshKey, bump } = useApp();
  const [d, setD] = useState(null);
  const [q, setQ] = useState("");
  const [uploading, setUploading] = useState(false);
  const [tab, setTab] = useState("all");
  const [missing, setMissing] = useState(null);

  const load = () => {
    const p = new URLSearchParams({ fy });
    if (q) p.set("q", q);
    api.get(`/documents?${p}`).then(({ data }) => setD(data)).catch(() => setD(false));
    api.get(`/documents/missing-receipts?fy=${fy}`).then(({ data }) => setMissing(data)).catch(() => {});
  };
  useEffect(() => { if (fy) load(); }, [fy, refreshKey, q]); // eslint-disable-line

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Uploaded"); bump();
    } catch (e) { toast.error(errText(e)); } finally { setUploading(false); }
  };

  const remove = async (id) => {
    try { await api.delete(`/documents/${id}`); toast.success("Document removed"); bump(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <Loading label="Loading documents" />;

  return (
    <div data-testid="documents-page">
      <PageHeader title="Document Vault" subtitle="Searchable receipts, invoices and supporting documents for every financial year.">
        <Label className="cursor-pointer inline-flex items-center gap-1.5 border border-border px-3 h-9 rounded-sm text-xs hover:bg-accent" data-testid="documents-upload">
          <Upload size={14} /> {uploading ? "Uploading…" : "Upload document"}
          <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => upload(e.target.files?.[0])} />
        </Label>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-4 border border-border bg-border mb-4">
        <KpiCard label="Documents" value={String(d.total)} testId="docs-count" />
        <KpiCard label="Missing Receipts" value={String(missing?.count ?? 0)} tone={missing?.count ? "warning" : "neutral"} testId="docs-missing-count" />
        <KpiCard label="Amount Missing Receipts" value={missing?.total_amount ?? 0} testId="docs-missing-amount" />
        <KpiCard label="Financial Year" value={fy?.replace("FY", "FY ")} testId="docs-fy" />
      </div>

      <div className="flex gap-2 mb-4">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search filename or notes…"
          className="rounded-sm max-w-sm text-sm" data-testid="docs-search" />
        <Button variant={tab === "all" ? "default" : "outline"} size="sm" className="rounded-sm" onClick={() => setTab("all")} data-testid="docs-tab-all">All documents</Button>
        <Button variant={tab === "missing" ? "default" : "outline"} size="sm" className="rounded-sm" onClick={() => setTab("missing")} data-testid="docs-tab-missing">Expenses missing receipts</Button>
      </div>

      {tab === "all" ? (
        <Section title={`${d.items.length} documents`} testId="docs-table">
          {d.items.length === 0 ? <Empty title="No documents yet" hint="Upload a receipt or attach one from a transaction." /> : (
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "Filename", "Type", "Linked to", "Size", ""].map((h, i) => (
                  <TableHead key={h + i} className={`overline ${i > 3 ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {d.items.map((doc) => (
                  <TableRow key={doc.document_id} data-testid={`doc-row-${doc.document_id}`}>
                    <TableCell className="num text-xs">{fmtDate(doc.date)}</TableCell>
                    <TableCell className="text-xs">
                      <button className="underline underline-offset-2 hover:text-primary" data-testid={`doc-download-${doc.document_id}`}
                        onClick={() => downloadFile(`/documents/${doc.document_id}/download`, doc.filename)}>
                        {doc.filename}
                      </button>
                    </TableCell>
                    <TableCell className="text-xs num">{doc.content_type}</TableCell>
                    <TableCell className="text-xs">{doc.linked_type ? doc.linked_type.replace("_", " ") : "Unlinked"}</TableCell>
                    <TableCell className="text-right num text-xs">{Math.round((doc.size || 0) / 1024)} KB</TableCell>
                    <TableCell className="text-right">
                      <button onClick={() => remove(doc.document_id)} data-testid={`doc-delete-${doc.document_id}`}
                        className="text-muted-foreground hover:text-negative"><Trash2 size={12} /></button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      ) : (
        <Section title={`Expenses missing receipts (${missing?.transactions?.length ?? 0})`} testId="docs-missing-table">
          {!missing?.transactions?.length ? <Empty title="Every expense has a receipt" /> : (
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "Category", "Supplier", "Description", "Amount"].map((h, i) => (
                  <TableHead key={h} className={`overline ${i === 4 ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {missing.transactions.map((t) => (
                  <TableRow key={t.txn_id} data-testid={`missing-receipt-${t.txn_id}`}>
                    <TableCell className="num text-xs">{fmtDate(t.date)}</TableCell>
                    <TableCell className="text-xs">{t.subcategory_name || t.category_name || "Uncategorised"}</TableCell>
                    <TableCell className="text-xs">{t.supplier_name || "—"}</TableCell>
                    <TableCell className="text-xs">{t.description || "—"}</TableCell>
                    <TableCell className="text-right"><Money value={t.amount_inc} className="text-xs" /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>
      )}
    </div>
  );
}

export function Reminders() {
  const { fy, refreshKey, bump } = useApp();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [addFor, setAddFor] = useState(null);

  const load = () => api.get(`/reminders?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  useEffect(() => { if (fy) load(); }, [fy, refreshKey]); // eslint-disable-line

  const scan = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/reminders/scan?fy=${fy}`);
      toast.success(`Scan complete — ${data.created} new reminder(s)`);
      load();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const act = async (id, action) => {
    try { await api.post(`/reminders/${id}/action`, { action, snooze_days: 7 }); load(); bump(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <Loading label="Loading reminders" />;

  return (
    <div data-testid="reminders-page">
      <PageHeader title="Missing / To Review"
        subtitle="The engine compares your recurring templates and detected monthly patterns against what you have actually entered.">
        <Button size="sm" onClick={scan} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="scan-reminders-btn">
          {busy ? "Scanning…" : "Run scan"}
        </Button>
      </PageHeader>

      <div className="grid grid-cols-3 md:grid-cols-5 border border-border bg-border mb-4">
        {["open", "completed", "skipped", "snoozed", "na"].map((s) => (
          <KpiCard key={s} label={s === "na" ? "Not applicable" : s} value={String(d.counts[s] || 0)}
            tone={s === "open" && d.counts[s] ? "warning" : "neutral"} testId={`reminder-count-${s}`} />
        ))}
      </div>

      <Section title={`${d.items.length} reminders`} testId="reminders-list">
        {d.items.length === 0 ? <Empty title="Nothing outstanding" hint="Run a scan after adding recurring expense templates in Settings." /> : (
          <div className="divide-y divide-border">
            {d.items.map((r) => (
              <div key={r.reminder_id} className="flex flex-wrap items-center gap-3 px-4 py-3" data-testid={`reminder-row-${r.reminder_id}`}>
                <div className="flex-1 min-w-[240px]">
                  <div className="text-sm">{r.message}</div>
                  <div className="overline mt-1">
                    {r.kind === "missing_recurring" ? "Recurring template" : "Detected pattern"}
                    {r.expected_amount ? ` · expected ~${fmtMoney(r.expected_amount, 0)}` : ""}
                  </div>
                </div>
                <Pill tone={r.status === "open" ? "warning" : r.status === "completed" ? "positive" : "neutral"}>{r.status}</Pill>
                <div className="flex gap-1.5">
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1" data-testid={`reminder-add-${r.reminder_id}`}
                    onClick={() => setAddFor(r)}><Plus size={11} /> Add transaction</Button>
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1" data-testid={`reminder-complete-${r.reminder_id}`}
                    onClick={() => act(r.reminder_id, "complete")}><CheckCircle2 size={11} /> Complete</Button>
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1" data-testid={`reminder-skip-${r.reminder_id}`}
                    onClick={() => act(r.reminder_id, "skip")}><XCircle size={11} /> Skip</Button>
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1" data-testid={`reminder-snooze-${r.reminder_id}`}
                    onClick={() => act(r.reminder_id, "snooze")}><Clock size={11} /> Snooze</Button>
                  <Button size="sm" variant="outline" className="rounded-sm h-7 text-[11px] gap-1" data-testid={`reminder-na-${r.reminder_id}`}
                    onClick={() => act(r.reminder_id, "na")}><BellOff size={11} /> N/A</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
      <div className="mt-4"><Disclaimer>Email reminders are Coming in Phase 5 — in-app reminders work now.</Disclaimer></div>

      {addFor && <ReminderQuickAdd reminder={addFor} onClose={() => { setAddFor(null); load(); }} />}
    </div>
  );
}

function ReminderQuickAdd({ reminder, onClose }) {
  const monthStart = `${reminder.month_key}-15`;
  return <QuickAdd type="expense" onClose={onClose} onSaved={onClose} defaults={{
    date: monthStart, category_id: reminder.category_id || "__none__",
    subcategory_id: reminder.subcategory_id || "__none__",
    amount: reminder.expected_amount ? String(reminder.expected_amount) : "",
    description: reminder.message?.split("—")[0]?.trim() || "",
  }} />;
}
