import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errText, fmtMoney, downloadFile } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Download, FileText } from "lucide-react";

const c = (cents) => fmtMoney((cents || 0) / 100);

export default function PayrollReports() {
  return (
    <div data-testid="payroll-reports-page">
      <PageHeader title="Payroll Reports" subtitle="Payroll Summary, Payment Summary, Super Payable and Leave Balances" />
      <Disclaimer>Reports read from finalised payslips and phase-4 ledgers only. Nothing is lodged with the ATO. Verify amounts with your accountant / registered tax agent.</Disclaimer>
      <Tabs defaultValue="summary" className="mt-4">
        <TabsList className="rounded-sm bg-muted h-9 flex-wrap h-auto">
          <TabsTrigger value="summary" className="rounded-sm text-xs" data-testid="rep-tab-summary">Payroll Summary</TabsTrigger>
          <TabsTrigger value="payment" className="rounded-sm text-xs" data-testid="rep-tab-payment">Payment Summary</TabsTrigger>
          <TabsTrigger value="super" className="rounded-sm text-xs" data-testid="rep-tab-super">Super by Quarter</TabsTrigger>
          <TabsTrigger value="leave" className="rounded-sm text-xs" data-testid="rep-tab-leave">Leave Balances</TabsTrigger>
        </TabsList>
        <TabsContent value="summary" className="mt-4"><SummaryReport /></TabsContent>
        <TabsContent value="payment" className="mt-4"><PaymentReport /></TabsContent>
        <TabsContent value="super" className="mt-4"><SuperReport /></TabsContent>
        <TabsContent value="leave" className="mt-4"><LeaveReport /></TabsContent>
      </Tabs>
    </div>
  );
}

function ExportButtons({ base, params = {}, testPrefix }) {
  const dl = async (ext) => {
    try {
      const q = new URLSearchParams(params).toString();
      await downloadFile(`/payroll/${base}.${ext}?${q}`, `${base.replace(/\//g, "-")}.${ext}`);
    } catch (e) { toast.error(errText(e)); }
  };
  return (
    <div className="flex gap-2">
      <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1"
        onClick={() => dl("csv")} data-testid={`${testPrefix}-csv`}><Download size={12} /> CSV</Button>
      <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1"
        onClick={() => dl("pdf")} data-testid={`${testPrefix}-pdf`}><FileText size={12} /> PDF</Button>
    </div>
  );
}

function SummaryReport() {
  const { fy } = useApp();
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [d, setD] = useState(null);
  const load = async () => {
    try {
      const p = new URLSearchParams();
      if (fy) p.set("fy", fy);
      if (start) p.set("period_start", start);
      if (end) p.set("period_end", end);
      const { data } = await api.get(`/payroll/reports/summary?${p.toString()}`);
      setD(data);
    } catch (e) { toast.error(errText(e)); setD({ rows: [], totals: {} }); }
  };
  useEffect(() => { if (fy) load(); }, [fy, start, end]); // eslint-disable-line

  const t = d?.totals || {};
  const params = { ...(fy && { fy }), ...(start && { period_start: start }), ...(end && { period_end: end }) };

  return (
    <Section title={`Payroll Summary · ${fy || ""}`} testId="report-summary"
      right={<ExportButtons base="reports/summary" params={params} testPrefix="rep-summary" />}>
      <div className="px-4 py-3 border-b border-border flex gap-2 flex-wrap">
        <div><Label className="overline">Period start</Label>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="rounded-sm num h-8" data-testid="rep-summary-start" /></div>
        <div><Label className="overline">Period end</Label>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="rounded-sm num h-8" data-testid="rep-summary-end" /></div>
      </div>
      {!d ? <Loading /> : d.rows.length === 0 ? <Empty title="No finalised payslips in this period" /> : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Employee", "Slips", "Gross", "Pre-tax Ded.", "Taxable", "PAYG", "Post-tax Ded.", "Net", "Super"].map((h) =>
                <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {d.rows.map((r) => (
                <TableRow key={r.employee_id}>
                  <TableCell className="text-xs">{r.employee_name}</TableCell>
                  <TableCell className="text-xs num text-right">{r.payslip_count}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.gross_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.pretax_ded_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.taxable_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.payg_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.posttax_ded_cents)}</TableCell>
                  <TableCell className="text-xs num text-right font-semibold">{c(r.net_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.super_cents)}</TableCell>
                </TableRow>
              ))}
              <TableRow className="bg-accent/40 font-semibold">
                <TableCell className="text-xs">TOTAL</TableCell>
                <TableCell className="text-xs num text-right">{t.payslip_count}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.gross_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.pretax_ded_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.taxable_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.payg_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.posttax_ded_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.net_cents)}</TableCell>
                <TableCell className="text-xs num text-right">{c(t.super_cents)}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}

function PaymentReport() {
  const { fy } = useApp();
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return;
    api.get(`/payroll/reports/payment-summary?fy=${fy}`).then(({ data }) => setD(data))
      .catch((e) => { setD({ rows: [] }); toast.error(errText(e)); });
  }, [fy]);
  return (
    <Section title={`Payment Summary (per employee) · ${fy || ""}`} testId="report-payment"
      right={<ExportButtons base="reports/payment-summary" params={{ fy }} testPrefix="rep-payment" />}>
      {!d ? <Loading /> : d.rows.length === 0 ? <Empty title="No finalised payslips in this FY" /> : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Employee", "Period", "Slips", "Gross", "Taxable", "PAYG", "Net", "Super"].map((h) =>
                <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {d.rows.map((r) => (
                <TableRow key={r.employee_id} data-testid={`payment-row-${r.employee_id}`}>
                  <TableCell className="text-xs">{r.employee_name}</TableCell>
                  <TableCell className="text-xs num">{r.period_start} → {r.period_end}</TableCell>
                  <TableCell className="text-xs num text-right">{r.payslip_count}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.gross_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.taxable_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.payg_cents)}</TableCell>
                  <TableCell className="text-xs num text-right font-semibold">{c(r.net_cents)}</TableCell>
                  <TableCell className="text-xs num text-right">{c(r.super_cents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}

function SuperReport() {
  const { fy } = useApp();
  const [quarter, setQuarter] = useState("all");
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return;
    const p = new URLSearchParams({ fy }); if (quarter !== "all") p.set("quarter", quarter);
    api.get(`/payroll/reports/super-quarter?${p.toString()}`).then(({ data }) => setD(data))
      .catch(() => setD({ quarters: [] }));
  }, [fy, quarter]);
  const params = { ...(fy && { fy }), ...(quarter !== "all" && { quarter }) };
  return (
    <Section title={`Super Payable · ${fy || ""}`} testId="report-super"
      right={<div className="flex gap-2 items-center">
        <Select value={quarter} onValueChange={setQuarter}>
          <SelectTrigger className="h-8 w-40 rounded-sm text-xs"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-popover">
            <SelectItem value="all">All quarters</SelectItem>
            {["Q1", "Q2", "Q3", "Q4"].map((q) => <SelectItem key={q} value={q}>{q}</SelectItem>)}
          </SelectContent>
        </Select>
        <ExportButtons base="reports/super-quarter" params={params} testPrefix="rep-super" />
      </div>}>
      {!d ? <Loading /> : (d.quarters || []).length === 0 ? <Empty title="No super liabilities in this period" /> : (
        <div className="p-4 space-y-6">
          {d.quarters.map((q) => (
            <div key={q.quarter} data-testid={`super-q-${q.quarter}`}>
              <div className="mb-2 flex items-baseline justify-between">
                <div className="font-serif text-lg">{q.quarter} · {q.period_start} → {q.period_end}</div>
                <div className="overline">Due {q.due_date}</div>
              </div>
              <Table>
                <TableHeader><TableRow className="hover:bg-transparent">
                  {["Employee", "Fund", "Accrued", "Paid", "Outstanding", "Status"].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
                </TableRow></TableHeader>
                <TableBody>
                  {q.employees.map((it) => (
                    <TableRow key={it.liability_id}>
                      <TableCell className="text-xs">{it.employee_name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{it.fund_name || "—"}</TableCell>
                      <TableCell className="text-xs num text-right">{c(it.accrued_cents)}</TableCell>
                      <TableCell className="text-xs num text-right">{c(it.paid_cents)}</TableCell>
                      <TableCell className="text-xs num text-right font-semibold">{c(it.outstanding_cents)}</TableCell>
                      <TableCell>{it.is_overdue ? <Pill tone="negative">Overdue</Pill> : <Pill tone={it.status === "paid" ? "positive" : "warning"}>{it.status}</Pill>}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="bg-accent/40 font-semibold">
                    <TableCell className="text-xs">TOTAL</TableCell>
                    <TableCell></TableCell>
                    <TableCell className="text-xs num text-right">{c(q.accrued_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(q.paid_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(q.outstanding_cents)}</TableCell>
                    <TableCell></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function LeaveReport() {
  const [d, setD] = useState(null);
  useEffect(() => {
    api.get("/payroll/reports/leave-balances").then(({ data }) => setD(data))
      .catch(() => setD({ rows: [] }));
  }, []);
  const types = Array.from(new Set((d?.rows || []).flatMap((r) => Object.keys(r.by_type || {})))).sort();
  return (
    <Section title="Leave Balances Snapshot" testId="report-leave"
      right={<ExportButtons base="reports/leave-balances" testPrefix="rep-leave" />}>
      {!d ? <Loading /> : d.rows.length === 0 ? <Empty title="No leave balances yet" hint="Configure leave settings on an employee to accrue and track hours." /> : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              <TableHead className="overline">Employee</TableHead>
              {types.map((t) => <TableHead key={t} className="overline capitalize">{t.replace("_", " ")}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {d.rows.map((r) => (
                <TableRow key={r.employee_id}>
                  <TableCell className="text-xs">{r.employee_name}</TableCell>
                  {types.map((t) => {
                    const b = r.by_type[t];
                    return (
                      <TableCell key={t} className="text-xs num text-right">
                        {b ? <>
                          <span className="font-semibold">{b.remaining_hours}</span>
                          <span className="text-muted-foreground text-[10px] block">acc {b.entitled_hours} · fut {b.future_approved_hours}</span>
                        </> : "—"}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}
