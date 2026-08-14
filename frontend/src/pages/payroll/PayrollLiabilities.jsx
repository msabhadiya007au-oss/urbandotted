import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertTriangle, DollarSign } from "lucide-react";

const c = (cents) => fmtMoney((cents || 0) / 100);

export default function PayrollLiabilities() {
  const { fy } = useApp();
  const [summary, setSummary] = useState(null);
  useEffect(() => {
    if (!fy) return;
    api.get(`/payroll/liabilities-summary?fy=${fy}`).then(({ data }) => setSummary(data))
      .catch(() => setSummary(false));
  }, [fy]);

  return (
    <div data-testid="payroll-liabilities-page">
      <PageHeader title="Payroll Liabilities" subtitle={`Wages, PAYG and Super owed — ${fy || ""}`} />
      <Disclaimer><AlertTriangle size={12} className="inline mr-1 -mt-0.5" /> Recording a payment closes the liability. It does NOT create an additional operating expense — the expense was recognised at pay-run finalisation.</Disclaimer>

      {summary && (
        <div className="grid gap-2 md:grid-cols-4 mt-6" data-testid="liabilities-summary">
          <Kpi label="Wages outstanding" value={c(summary.wages_outstanding_cents)} tone={summary.wages_outstanding_cents > 0 ? "warning" : "neutral"} />
          <Kpi label="PAYG outstanding" value={c(summary.payg_outstanding_cents)} tone={summary.payg_outstanding_cents > 0 ? "warning" : "neutral"} />
          <Kpi label="Super outstanding" value={c(summary.super_outstanding_cents)} tone={summary.super_outstanding_cents > 0 ? "warning" : "neutral"} />
          <Kpi label="Total" value={c(summary.total_outstanding_cents)} tone={summary.total_outstanding_cents > 0 ? "negative" : "positive"} />
        </div>
      )}

      <Tabs defaultValue="wages" className="mt-6">
        <TabsList className="rounded-sm bg-muted h-9">
          <TabsTrigger value="wages" className="rounded-sm text-xs" data-testid="tab-wages">Wages payable</TabsTrigger>
          <TabsTrigger value="payg" className="rounded-sm text-xs" data-testid="tab-payg">PAYG owed</TabsTrigger>
        </TabsList>
        <TabsContent value="wages" className="mt-4"><LiabilityList kind="wages" /></TabsContent>
        <TabsContent value="payg" className="mt-4"><LiabilityList kind="payg" /></TabsContent>
      </Tabs>
    </div>
  );
}

function LiabilityList({ kind }) {
  const { fy } = useApp();
  const [items, setItems] = useState(null);
  const [payFor, setPayFor] = useState(null);
  const endpointList = kind === "wages" ? "/payroll/wages-payables" : "/payroll/payg-liabilities";
  const payEndpoint = (id) => kind === "wages"
    ? `/payroll/wages-payables/${id}/pay`
    : `/payroll/payg-liabilities/${id}/pay`;
  const idField = kind === "wages" ? "payable_id" : "liability_id";
  const amountField = kind === "wages" ? "net_cents" : "payg_cents";
  const load = async () => {
    try {
      const p = new URLSearchParams(); if (fy) p.set("fy", fy);
      const { data } = await api.get(`${endpointList}?${p.toString()}`);
      setItems(data.items || []);
    } catch (e) { setItems([]); toast.error(errText(e)); }
  };
  useEffect(() => { if (fy) load(); }, [fy]); // eslint-disable-line

  return (
    <Section title={kind === "wages" ? "Wages payable to employees" : "PAYG owed to ATO"} testId={`liab-${kind}-list`}>
      {items === null ? <Loading /> : items.length === 0 ? (
        <Empty title="Nothing outstanding" hint="Payroll liabilities are created when a pay run is finalised." />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Pay Run", "Payment date", "Amount", "Paid", "Outstanding", "Status", ""].map((h) =>
                <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {items.map((r) => {
                const total = int(r[amountField]);
                const paid = int(r.paid_cents);
                const out = Math.max(0, total - paid);
                const isVoided = r.status === "voided";
                return (
                  <TableRow key={r[idField]} data-testid={`liab-row-${r[idField]}`}>
                    <TableCell className="text-xs num">{r.pay_run_ref}</TableCell>
                    <TableCell className="text-xs num">{r.payment_date}</TableCell>
                    <TableCell className="text-xs num text-right">{c(total)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(paid)}</TableCell>
                    <TableCell className="text-xs num text-right font-semibold">{c(out)}</TableCell>
                    <TableCell><Pill tone={r.status === "paid" ? "positive" : isVoided ? "neutral" : "warning"}>{r.status}</Pill></TableCell>
                    <TableCell>
                      {out > 0 && !isVoided && (
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          onClick={() => setPayFor({ ...r, __outstanding: out })}
                          data-testid={`liab-pay-btn-${r[idField]}`}>
                          <DollarSign size={11} /> Mark paid
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      {payFor && <PayDialog row={payFor} endpoint={payEndpoint(payFor[idField])}
                             onClose={() => setPayFor(null)}
                             onSaved={() => { setPayFor(null); load(); }} />}
    </Section>
  );
}

function int(v) { return typeof v === "number" ? v : parseInt(v || "0", 10); }

function Kpi({ label, value, tone = "neutral" }) {
  const cls = tone === "positive" ? "text-positive" : tone === "warning" ? "text-warning" : tone === "negative" ? "text-negative" : "text-foreground";
  return (
    <div className={`border border-border p-3 bg-card ${tone === "warning" ? "bg-warning/5" : tone === "negative" ? "bg-negative/5" : ""}`}>
      <div className="overline">{label}</div>
      <div className={`num text-sm font-semibold mt-1 ${cls}`}>{value ?? "—"}</div>
    </div>
  );
}

function PayDialog({ row, endpoint, onClose, onSaved }) {
  const [f, setF] = useState({
    paid_dollars: ((row.__outstanding || 0) / 100).toFixed(2),
    payment_date: new Date().toISOString().slice(0, 10),
    payment_reference: "", payment_note: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(endpoint, {
        paid_cents: Math.round(parseFloat(f.paid_dollars || "0") * 100),
        payment_date: f.payment_date,
        payment_reference: f.payment_reference, payment_note: f.payment_note,
      });
      toast.success("Payment recorded");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="liab-pay-dialog">
        <DialogHeader><DialogTitle>Record payment</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">{row.pay_run_ref} · outstanding {(row.__outstanding / 100).toFixed(2)}</p>
        <div className="grid gap-3 mt-2">
          <div><Label className="overline">Amount ($)</Label>
            <Input type="number" step="0.01" value={f.paid_dollars}
              onChange={(e) => setF({ ...f, paid_dollars: e.target.value })}
              className="rounded-sm num" data-testid="liab-pay-amount" /></div>
          <div><Label className="overline">Payment date</Label>
            <Input type="date" value={f.payment_date}
              onChange={(e) => setF({ ...f, payment_date: e.target.value })}
              className="rounded-sm num" data-testid="liab-pay-date" /></div>
          <div><Label className="overline">Reference</Label>
            <Input value={f.payment_reference}
              onChange={(e) => setF({ ...f, payment_reference: e.target.value })}
              placeholder="Bank ref / BAS ref" className="rounded-sm" data-testid="liab-pay-ref" /></div>
          <div><Label className="overline">Note</Label>
            <Input value={f.payment_note}
              onChange={(e) => setF({ ...f, payment_note: e.target.value })}
              className="rounded-sm" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="liab-pay-submit">
            {busy ? "Saving…" : "Record payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
