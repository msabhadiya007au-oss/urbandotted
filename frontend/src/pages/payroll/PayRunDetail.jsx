import React, { useEffect, useState, useMemo } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ArrowLeft, Trash2, Plus, Lock, XCircle } from "lucide-react";

const c = (cents) => fmtMoney((cents || 0) / 100);
const STATUS_TONES = { draft: "warning", calculated: "warning", finalised: "positive", voided: "neutral" };
const IMMUTABLE = new Set(["finalised", "voided"]);

export default function PayRunDetail() {
  const { ref } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState(null);
  const [voidOpen, setVoidOpen] = useState(false);

  const load = async () => {
    try { const { data } = await api.get(`/payroll/pay-runs/${ref}`); setRun(data); }
    catch (e) { toast.error(errText(e)); setRun(false); }
  };
  useEffect(() => { load(); }, [ref]); // eslint-disable-line react-hooks/exhaustive-deps

  if (run === null) return <Loading label="Loading pay run" />;
  if (run === false) return <div className="text-sm">Not found. <Link to="/payroll/pay-runs" className="underline">Back</Link></div>;

  const immutable = IMMUTABLE.has(run.status);
  const finalise = async () => {
    if (!window.confirm("Finalise this pay run? Once finalised it cannot be edited — only voided.")) return;
    try { await api.post(`/payroll/pay-runs/${ref}/finalise`); toast.success("Pay run finalised"); load(); }
    catch (e) { toast.error(errText(e)); }
  };
  const reload = async () => { try { await api.post(`/payroll/pay-runs/${ref}/load`); toast.success("Employees reloaded"); load(); } catch (e) { toast.error(errText(e)); } };

  const t = run.totals || {};
  return (
    <div data-testid="pay-run-detail-page">
      <div className="mb-2 -mt-2">
        <Link to="/payroll/pay-runs" className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft size={12} /> Pay Runs
        </Link>
      </div>
      <PageHeader
        title={run.pay_run_ref}
        subtitle={`${run.pay_frequency} · ${run.period_start} → ${run.period_end} · pay ${run.payment_date}`}
        right={<div className="flex gap-2 items-center">
          <Pill tone={STATUS_TONES[run.status]}>{run.status}</Pill>
          {!immutable && <Button size="sm" variant="outline" className="rounded-sm text-xs" onClick={reload} data-testid="pay-run-reload">Reload employees</Button>}
          {!immutable && <Button size="sm" className="rounded-sm bg-primary text-primary-foreground text-xs gap-1.5" onClick={finalise} data-testid="pay-run-finalise"><Lock size={12} /> Finalise</Button>}
          {run.status === "finalised" && <Button asChild size="sm" variant="outline" className="rounded-sm text-xs"><Link to="/payroll/payslips" data-testid="pay-run-payslips">View payslips</Link></Button>}
          {run.status === "finalised" && <Button size="sm" variant="outline" className="rounded-sm text-xs text-negative gap-1.5" onClick={() => setVoidOpen(true)} data-testid="pay-run-void"><XCircle size={12} /> Void</Button>}
        </div>}
      />

      <div className="grid gap-2 md:grid-cols-6 mb-4">
        <TotalCard label="Employees" value={t.employee_count || 0} raw />
        <TotalCard label="Gross" value={c(t.gross_cents)} />
        <TotalCard label="PAYG" value={c(t.payg_cents)} />
        <TotalCard label="Net" value={c(t.net_cents)} />
        <TotalCard label="Super" value={c(t.super_cents)} />
        <TotalCard label="Employer cost" value={c(t.total_employer_cost_cents)} strong />
      </div>

      <Disclaimer>PAYG is entered manually per employee. This deployment does not include verified ATO tax tables. Review before finalising.</Disclaimer>

      <Section title="Employees in this pay run" testId="pay-run-employees">
        {(run.employees || []).length === 0 ? (
          <Empty title="No eligible employees for this frequency" hint="Add active employees with a matching pay-settings row, then Reload." />
        ) : (
          <div className="divide-y divide-border">
            {run.employees.map((e) => (
              <EmployeeEditor key={e.employee_id} pr={run} row={e} immutable={immutable} onSaved={load} />
            ))}
          </div>
        )}
      </Section>

      {voidOpen && <VoidDialog ref_={ref} onClose={() => setVoidOpen(false)} onVoided={() => { setVoidOpen(false); load(); }} />}
    </div>
  );
}

function TotalCard({ label, value, strong, raw }) {
  return (
    <div className={`border border-border p-3 ${strong ? "bg-accent/30" : ""}`}>
      <div className="overline">{label}</div>
      <div className={`num mt-1 ${strong ? "text-sm font-semibold" : "text-sm"}`}>{raw ? value : value}</div>
    </div>
  );
}

function VoidDialog({ ref_, onClose, onVoided }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api.post(`/payroll/pay-runs/${ref_}/void`, { reason }); toast.success("Pay run voided"); onVoided(); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card">
        <DialogHeader><DialogTitle>Void pay run</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">Voiding preserves the historical record and excludes it from active totals. It cannot be undone.</p>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" className="rounded-sm mt-3" data-testid="void-reason" />
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !reason.trim()} className="rounded-sm bg-negative text-white" data-testid="void-submit">
            {busy ? "Voiding…" : "Void pay run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function blankLine() {
  return {
    pay_item_id: null, code: "", label: "", kind: "earning", calc_type: "hourly",
    hours_or_units: "0", rate_cents: 0, base_rate_cents: null,
    taxable: true, super_liable: true, deduction_category: null,
    date: null, amount_cents_override: null,
  };
}

function EmployeeEditor({ pr, row, immutable, onSaved }) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState(row.lines || []);
  const [paygDollars, setPaygDollars] = useState(
    row.payg_override_cents != null ? (row.payg_override_cents / 100).toString() : (row.manual_payg_default || "0")
  );
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLines(row.lines || []);
    setPaygDollars(row.payg_override_cents != null ? (row.payg_override_cents / 100).toString() : (row.manual_payg_default || "0"));
  }, [row]);

  const totals = useMemo(() => {
    let gross = 0, superable = 0, pre = 0, post = 0;
    lines.forEach((L) => {
      const amt = L.amount_cents_override != null ? +L.amount_cents_override
        : (L.calc_type === "fixed" ? +L.rate_cents
           : Math.round(parseFloat(L.hours_or_units || "0") * (+L.rate_cents || 0)));
      if (L.kind === "earning") { gross += amt; if (L.super_liable) superable += amt; }
      else if (L.kind === "deduction") {
        if (L.deduction_category === "pretax") pre += amt; else post += amt;
      }
    });
    const taxable = Math.max(0, gross - pre);
    const payg = Math.max(0, Math.round(parseFloat(paygDollars || "0") * 100));
    const paygApplied = Math.min(payg, taxable);
    const net = taxable - paygApplied - post;
    const rate = parseFloat(row.sg_rate || "0.12") || 0;
    const sup = superable > 0 ? Math.round(superable * rate) : 0;
    return { gross, superable, pre, post, taxable, payg: paygApplied, net, sup };
  }, [lines, paygDollars, row.sg_rate]);

  const save = async () => {
    setBusy(true);
    try {
      const paygCents = Math.max(0, Math.round(parseFloat(paygDollars || "0") * 100));
      await api.put(`/payroll/pay-runs/${pr.pay_run_ref}/employees/${row.employee_id}`, {
        lines, payg_override_cents: paygCents, sg_rate: row.sg_rate,
      });
      toast.success("Recalculated"); onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const updateLine = (i, patch) => setLines(lines.map((L, k) => k === i ? { ...L, ...patch } : L));
  const addLine = (kind = "earning") => setLines([...lines, { ...blankLine(), kind }]);
  const removeLine = (i) => setLines(lines.filter((_, k) => k !== i));

  return (
    <div className="px-4 py-3" data-testid={`emp-row-${row.employee_id}`}>
      <div className="flex items-center gap-3 flex-wrap">
        <button type="button" onClick={() => setOpen(!open)} className="text-xs text-muted-foreground hover:text-foreground" data-testid={`emp-toggle-${row.employee_id}`}>
          {open ? "▼" : "▶"}
        </button>
        <div className="flex-1 min-w-[180px]">
          <div className="text-sm font-semibold">{row.employee_name}</div>
          <div className="overline">{(row.pay_basis || "").replace("_", " ")} · {row.pay_frequency}</div>
        </div>
        <div className="text-xs num text-right"><span className="overline block">Gross</span>{c(totals.gross)}</div>
        <div className="text-xs num text-right"><span className="overline block">PAYG</span>{c(totals.payg)}</div>
        <div className="text-xs num text-right"><span className="overline block">Net</span>{c(totals.net)}</div>
        <div className="text-xs num text-right"><span className="overline block">Super</span>{c(totals.sup)}</div>
      </div>

      {open && (
        <div className="mt-3 border border-border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Kind", "Code", "Label", "Calc", "Hours/Units", "Rate", "Amount", "Tax", "Super", ""].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {lines.map((L, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs">
                      <Select value={L.kind} onValueChange={(v) => updateLine(i, { kind: v, deduction_category: v === "deduction" ? (L.deduction_category || "posttax") : null })}>
                        <SelectTrigger className="h-8 w-28 rounded-sm text-xs" disabled={immutable}><SelectValue /></SelectTrigger>
                        <SelectContent className="bg-popover">
                          {[["earning", "Earning"], ["deduction", "Deduction"]].map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                        </SelectContent>
                      </Select></TableCell>
                    <TableCell><Input value={L.code} onChange={(e) => updateLine(i, { code: e.target.value })} className="h-8 w-20 rounded-sm text-xs num" disabled={immutable} /></TableCell>
                    <TableCell><Input value={L.label} onChange={(e) => updateLine(i, { label: e.target.value })} className="h-8 w-36 rounded-sm text-xs" disabled={immutable} /></TableCell>
                    <TableCell>
                      <Select value={L.calc_type} onValueChange={(v) => updateLine(i, { calc_type: v })}>
                        <SelectTrigger className="h-8 w-32 rounded-sm text-xs" disabled={immutable}><SelectValue /></SelectTrigger>
                        <SelectContent className="bg-popover">
                          {[["hourly", "Hourly"], ["fixed", "Fixed"], ["percent_of_base", "% of base"], ["percent_loading", "% loading"], ["units_rate", "Units×rate"]].map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                        </SelectContent>
                      </Select></TableCell>
                    <TableCell><Input type="number" step="0.01" min="0" value={L.hours_or_units} onChange={(e) => updateLine(i, { hours_or_units: e.target.value })} className="h-8 w-24 rounded-sm text-xs num" disabled={immutable} data-testid={`line-hours-${i}`} /></TableCell>
                    <TableCell><Input type="number" step="1" min="0" value={L.rate_cents}
                      onChange={(e) => updateLine(i, { rate_cents: parseInt(e.target.value || "0", 10) })}
                      className="h-8 w-28 rounded-sm text-xs num" disabled={immutable} title="in cents" /></TableCell>
                    <TableCell className="text-xs num text-right">{c(L.amount_cents_override != null ? L.amount_cents_override : (L.calc_type === "fixed" ? L.rate_cents : Math.round(parseFloat(L.hours_or_units || "0") * (+L.rate_cents || 0))))}</TableCell>
                    <TableCell><Switch checked={!!L.taxable} onCheckedChange={(v) => updateLine(i, { taxable: v })} disabled={immutable} /></TableCell>
                    <TableCell><Switch checked={!!L.super_liable} onCheckedChange={(v) => updateLine(i, { super_liable: v })} disabled={immutable} /></TableCell>
                    <TableCell><button type="button" onClick={() => removeLine(i)} disabled={immutable} className="text-muted-foreground hover:text-negative"><Trash2 size={12} /></button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {!immutable && (
            <div className="flex gap-2 flex-wrap p-3 border-t border-border items-end">
              <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1" onClick={() => addLine("earning")} data-testid={`add-earning-${row.employee_id}`}><Plus size={12} /> Earning</Button>
              <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1" onClick={() => addLine("deduction")}><Plus size={12} /> Deduction</Button>
              <div className="ml-auto flex gap-2 items-end">
                <div><Label className="overline">Manual PAYG ($)</Label><Input value={paygDollars} onChange={(e) => setPaygDollars(e.target.value)} className="h-8 w-28 rounded-sm text-xs num" data-testid={`payg-${row.employee_id}`} /></div>
                <Button size="sm" onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid={`emp-save-${row.employee_id}`}>{busy ? "Saving…" : "Save & recalc"}</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
