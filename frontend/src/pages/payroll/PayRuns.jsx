import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Pill } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus } from "lucide-react";

const STATUS_TONES = { draft: "warning", calculated: "warning", finalised: "positive", voided: "neutral" };

export default function PayRuns() {
  const { fy } = useApp();
  const [list, setList] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [openNew, setOpenNew] = useState(false);

  const load = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      if (fy) params.set("fy", fy);
      const { data } = await api.get(`/payroll/pay-runs?${params.toString()}`);
      setList(data.items || []);
    } catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [statusFilter, fy]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div data-testid="pay-runs-page">
      <PageHeader title="Pay Runs" subtitle={`Australian pay runs · ${fy || ""}`}
        right={<Button size="sm" className="rounded-sm bg-primary text-primary-foreground gap-1.5"
          onClick={() => setOpenNew(true)} data-testid="pay-run-new"><Plus size={14} /> New Pay Run</Button>} />

      <Section title={`Pay runs ${list ? `(${list.length})` : ""}`} testId="pay-runs-list">
        <div className="px-4 py-3 border-b border-border flex gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="pay-runs-status"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value="all">All statuses</SelectItem>
              {["draft", "calculated", "finalised", "voided"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {list === null ? <Loading /> : list.length === 0 ? (
          <Empty title="No pay runs yet" hint="Create a pay run to load eligible employees and calculate wages." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Ref", "Frequency", "Period", "Payment", "Employees", "Gross", "Net", "Super", "Status"].map((h) =>
                  <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {list.map((r) => (
                  <TableRow key={r.pay_run_ref} data-testid={`pay-run-row-${r.pay_run_ref}`}>
                    <TableCell className="text-xs num font-semibold">
                      <Link to={`/payroll/pay-runs/${r.pay_run_ref}`} className="hover:underline">{r.pay_run_ref}</Link>
                    </TableCell>
                    <TableCell className="text-xs capitalize">{r.pay_frequency}</TableCell>
                    <TableCell className="text-xs num">{r.period_start} → {r.period_end}</TableCell>
                    <TableCell className="text-xs num">{r.payment_date}</TableCell>
                    <TableCell className="text-xs num text-right">{r.totals?.employee_count || 0}</TableCell>
                    <TableCell className="text-xs num text-right">{fmtMoney((r.totals?.gross_cents || 0) / 100)}</TableCell>
                    <TableCell className="text-xs num text-right">{fmtMoney((r.totals?.net_cents || 0) / 100)}</TableCell>
                    <TableCell className="text-xs num text-right">{fmtMoney((r.totals?.super_cents || 0) / 100)}</TableCell>
                    <TableCell><Pill tone={STATUS_TONES[r.status] || "neutral"}>{r.status}</Pill></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {openNew && <NewPayRunDialog onClose={() => setOpenNew(false)} onCreated={(ref) => setOpenNew(false) || load()} />}
    </div>
  );
}

function NewPayRunDialog({ onClose, onCreated }) {
  const navigate = useNavigate();
  const [f, setF] = useState({ pay_frequency: "fortnightly", period_start: "", period_end: "", payment_date: "", notes: "" });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/payroll/pay-runs", f);
      toast.success(`Draft ${data.pay_run_ref} created`);
      // Auto-load eligible employees
      try { await api.post(`/payroll/pay-runs/${data.pay_run_ref}/load`); } catch (e) { /* ignore, editor will show empty */ }
      onCreated(data.pay_run_ref);
      navigate(`/payroll/pay-runs/${data.pay_run_ref}`);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="pay-run-new-dialog">
        <DialogHeader><DialogTitle>New pay run</DialogTitle></DialogHeader>
        <div className="grid gap-3 mt-2">
          <div><Label className="overline">Pay frequency</Label>
            <Select value={f.pay_frequency} onValueChange={(v) => setF({ ...f, pay_frequency: v })}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="pay-run-freq"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">
                {[["weekly", "Weekly"], ["fortnightly", "Fortnightly"], ["monthly", "Monthly"]].map(([v, l]) =>
                  <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select></div>
          <div><Label className="overline">Period start</Label>
            <Input type="date" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} className="rounded-sm num" data-testid="pay-run-start" /></div>
          <div><Label className="overline">Period end</Label>
            <Input type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} className="rounded-sm num" data-testid="pay-run-end" /></div>
          <div><Label className="overline">Payment date</Label>
            <Input type="date" value={f.payment_date} onChange={(e) => setF({ ...f, payment_date: e.target.value })} className="rounded-sm num" data-testid="pay-run-payment" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !f.period_start || !f.period_end || !f.payment_date}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="pay-run-create-submit">
            {busy ? "Creating…" : "Create pay run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
