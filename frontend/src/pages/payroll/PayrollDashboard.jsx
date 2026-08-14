import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Pill, Disclaimer, Loading, Empty } from "@/components/shared";
import { Users, Settings as SettingsIcon, ClipboardList, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const c = (cents) => fmtMoney((cents || 0) / 100);

export default function PayrollDashboard() {
  const { fy } = useApp();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!fy) return;
    api.get(`/payroll/dashboard?fy=${fy}`).then(({ data }) => setData(data)).catch((e) => { setData(false); toast.error(errText(e)); });
  }, [fy]);

  return (
    <div data-testid="payroll-dashboard-page">
      <PageHeader
        title="Payroll"
        subtitle={`Australian payroll · ${fy || ""}`}
        right={
          <div className="flex gap-2">
            <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
              <Link to="/payroll/employees" data-testid="go-employees"><Users size={12} className="mr-1" /> Employees</Link>
            </Button>
            <Button asChild size="sm" className="rounded-sm text-xs bg-primary text-primary-foreground">
              <Link to="/payroll/pay-runs" data-testid="go-pay-runs"><ClipboardList size={12} className="mr-1" /> Pay Runs</Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-2 md:grid-cols-3 mb-6">
        <Pill tone="warning" testId="pill-stp">STP: Not connected</Pill>
        <Pill tone="warning" testId="pill-payg">PAYG: Manual — verify tax tables</Pill>
        <Pill tone="neutral" testId="pill-super">Super: Tracked, not transferred</Pill>
      </div>

      {data === null ? <Loading /> : data === false ? <Empty title="Unable to load dashboard" /> : (
        <>
          <div className="grid gap-2 md:grid-cols-5 mb-6" data-testid="payroll-kpis">
            <Kpi label="Active employees" value={data.active_employees} />
            <Kpi label="Draft pay runs" value={data.drafts_count} tone={data.drafts_count > 0 ? "warning" : "neutral"} />
            <Kpi label={`YTD Gross (${data.fy})`} value={c(data.ytd?.gross_cents)} />
            <Kpi label="YTD Net" value={c(data.ytd?.net_cents)} />
            <Kpi label="YTD Super" value={c(data.ytd?.super_cents)} />
          </div>

          <Section title="Recent finalised pay runs" testId="recent-runs">
            {(data.recent_finalised || []).length === 0 ? (
              <Empty title="No finalised pay runs in this FY yet" hint="Create and finalise a pay run to see it here." />
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow className="hover:bg-transparent">
                    {["Ref", "Period", "Payment", "Gross", "PAYG", "Net", "Super"].map((h) =>
                      <TableHead key={h} className="overline">{h}</TableHead>)}
                  </TableRow></TableHeader>
                  <TableBody>
                    {data.recent_finalised.map((r) => (
                      <TableRow key={r.pay_run_ref}>
                        <TableCell className="text-xs num"><Link to={`/payroll/pay-runs/${r.pay_run_ref}`} className="font-semibold hover:underline">{r.pay_run_ref}</Link></TableCell>
                        <TableCell className="text-xs num">{r.period_start} → {r.period_end}</TableCell>
                        <TableCell className="text-xs num">{r.payment_date}</TableCell>
                        <TableCell className="text-xs num text-right">{c(r.totals?.gross_cents)}</TableCell>
                        <TableCell className="text-xs num text-right">{c(r.totals?.payg_cents)}</TableCell>
                        <TableCell className="text-xs num text-right">{c(r.totals?.net_cents)}</TableCell>
                        <TableCell className="text-xs num text-right">{c(r.totals?.super_cents)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </Section>
        </>
      )}

      <div className="mt-6">
        <Disclaimer>
          <AlertTriangle size={12} className="inline mr-1 -mt-0.5" /> Payroll is bookkeeping software. It does not lodge STP, remit PAYG, transfer super, or assess Fair Work / Award classifications. You remain responsible for legal compliance.
        </Disclaimer>
      </div>

      <div className="mt-4">
        <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
          <Link to="/settings" data-testid="go-payroll-settings"><SettingsIcon size={12} className="mr-1" /> Open Payroll Settings</Link>
        </Button>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone = "neutral" }) {
  return (
    <div className={`border border-border p-3 ${tone === "warning" ? "bg-warning/5" : ""}`}>
      <div className="overline">{label}</div>
      <div className="num text-sm font-semibold mt-1">{value ?? "—"}</div>
    </div>
  );
}
