import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, DollarSign } from "lucide-react";

const c = (cents) => fmtMoney((cents || 0) / 100);
const QUARTERS = [["all", "All quarters"], ["Q1", "Q1 · Jul-Sep"], ["Q2", "Q2 · Oct-Dec"], ["Q3", "Q3 · Jan-Mar"], ["Q4", "Q4 · Apr-Jun"]];

export default function SuperLiabilities() {
  const { fy } = useApp();
  const [list, setList] = useState(null);
  const [totals, setTotals] = useState(null);
  const [quarter, setQuarter] = useState("all");
  const [status, setStatus] = useState("all");
  const [payFor, setPayFor] = useState(null);

  const load = async () => {
    try {
      const p = new URLSearchParams();
      if (fy) p.set("fy", fy);
      if (quarter !== "all") p.set("quarter", quarter);
      if (status !== "all") p.set("status", status);
      const { data } = await api.get(`/payroll/super-liabilities?${p.toString()}`);
      setList(data.items || []);
      setTotals(data.totals || null);
    } catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { if (fy) load(); }, [fy, quarter, status]); // eslint-disable-line

  return (
    <div data-testid="super-liabilities-page">
      <PageHeader title="Super Liabilities" subtitle={`Tracked super — payments are NOT transferred automatically · ${fy || ""}`} />
      <Disclaimer><AlertTriangle size={12} className="inline mr-1 -mt-0.5" /> Employer super is a liability from finalised pay runs. Record a payment once you transfer super to the fund. Historical payslips are never modified.</Disclaimer>

      {totals && (
        <div className="grid gap-2 md:grid-cols-4 mt-6" data-testid="super-totals">
          <Kpi label="Accrued (FY)" value={c(totals.accrued_cents)} />
          <Kpi label="Paid" value={c(totals.paid_cents)} tone="positive" />
          <Kpi label="Outstanding" value={c(totals.outstanding_cents)} tone={totals.outstanding_cents > 0 ? "warning" : "neutral"} />
          <Kpi label="Overdue quarters" value={totals.overdue_count} tone={totals.overdue_count > 0 ? "negative" : "neutral"} />
        </div>
      )}

      <Section title={`Liabilities ${list ? `(${list.length})` : ""}`} className="mt-6" testId="super-list">
        <div className="px-4 py-3 border-b border-border flex gap-2">
          <Select value={quarter} onValueChange={setQuarter}>
            <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="super-quarter-filter"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">{QUARTERS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="super-status-filter"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value="all">All statuses</SelectItem>
              {["accrued", "partial", "paid"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {list === null ? <Loading /> : list.length === 0 ? (
          <Empty title="No super liabilities yet" hint="Finalise a pay run to accrue employer super here." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Quarter", "Employee", "Fund", "Rate", "Due date", "Accrued", "Paid", "Outstanding", "Status", ""].map((h) =>
                  <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {list.map((r) => (
                  <TableRow key={r.liability_id} data-testid={`super-row-${r.liability_id}`}>
                    <TableCell className="text-xs num">{r.quarter}</TableCell>
                    <TableCell className="text-xs">{r.employee_name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{r.fund_name || "—"}</TableCell>
                    <TableCell className="text-xs num">{r.sg_rate}</TableCell>
                    <TableCell className="text-xs num">{r.due_date}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.accrued_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.paid_cents)}</TableCell>
                    <TableCell className="text-xs num text-right font-semibold">{c(r.outstanding_cents)}</TableCell>
                    <TableCell>
                      {r.is_overdue ? <Pill tone="negative">Overdue</Pill> : <Pill tone={r.status === "paid" ? "positive" : "warning"}>{r.status}</Pill>}
                    </TableCell>
                    <TableCell>
                      {r.status !== "paid" && (
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          onClick={() => setPayFor(r)} data-testid={`super-pay-btn-${r.liability_id}`}>
                          <DollarSign size={11} /> Record payment
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {payFor && <PayDialog row={payFor} onClose={() => setPayFor(null)} onSaved={() => { setPayFor(null); load(); }} />}
    </div>
  );
}

function Kpi({ label, value, tone = "neutral" }) {
  const cls = tone === "positive" ? "text-positive" : tone === "warning" ? "text-warning" : tone === "negative" ? "text-negative" : "text-foreground";
  return (
    <div className="border border-border p-3 bg-card">
      <div className="overline">{label}</div>
      <div className={`num text-sm font-semibold mt-1 ${cls}`}>{value ?? "—"}</div>
    </div>
  );
}

function PayDialog({ row, onClose, onSaved }) {
  const [f, setF] = useState({
    paid_dollars: ((row.outstanding_cents || 0) / 100).toFixed(2),
    payment_date: new Date().toISOString().slice(0, 10),
    payment_reference: "", payment_note: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const paid_cents = Math.round(parseFloat(f.paid_dollars || "0") * 100);
      await api.post(`/payroll/super-liabilities/${row.liability_id}/pay`, {
        paid_cents, payment_date: f.payment_date,
        payment_reference: f.payment_reference, payment_note: f.payment_note,
      });
      toast.success("Super payment recorded");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="super-pay-dialog">
        <DialogHeader><DialogTitle>Record super payment</DialogTitle></DialogHeader>
        <div className="text-xs text-muted-foreground mb-2">{row.employee_name} · {row.quarter} · Outstanding {c(row.outstanding_cents)}</div>
        <div className="grid gap-3">
          <div><Label className="overline">Amount ($)</Label>
            <Input type="number" step="0.01" value={f.paid_dollars} onChange={(e) => setF({ ...f, paid_dollars: e.target.value })} className="rounded-sm num" data-testid="super-pay-amount" /></div>
          <div><Label className="overline">Payment date</Label>
            <Input type="date" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} className="rounded-sm num" data-testid="super-pay-date" /></div>
          <div><Label className="overline">Reference</Label>
            <Input value={f.payment_reference} onChange={(e) => setF({ ...f, payment_reference: e.target.value })} placeholder="Bank ref / clearing house ID" className="rounded-sm" data-testid="super-pay-ref" /></div>
          <div><Label className="overline">Note</Label>
            <Input value={f.payment_note} onChange={(e) => setF({ ...f, payment_note: e.target.value })} className="rounded-sm" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="super-pay-submit">
            {busy ? "Saving…" : "Record payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
