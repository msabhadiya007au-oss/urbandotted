import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errText, fmtMoney } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Pill, Disclaimer, Loading, Empty, MonthBarChart } from "@/components/shared";
import { Users, Settings as SettingsIcon, ClipboardList, AlertTriangle,
         PiggyBank, CalendarClock, FileText, ArrowRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const c = (cents) => fmtMoney((cents || 0) / 100);
const short = (mk) => {
  if (!mk) return "";
  const [y, m] = mk.split("-");
  return `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][parseInt(m,10)-1]} ${y.slice(2)}`;
};

export default function PayrollDashboard() {
  const { fy } = useApp();
  const [data, setData] = useState(null);
  const [scanning, setScanning] = useState(false);

  const load = () => {
    if (!fy) return;
    api.get(`/payroll/dashboard-full?fy=${fy}`).then(({ data }) => setData(data))
      .catch((e) => { setData(false); toast.error(errText(e)); });
  };
  useEffect(() => { load(); }, [fy]); // eslint-disable-line

  const scan = async () => {
    setScanning(true);
    try {
      const { data } = await api.post("/payroll/reminders/scan");
      toast.success(`Created ${data.created} new payroll reminders`);
      load();
    } catch (e) { toast.error(errText(e)); } finally { setScanning(false); }
  };

  const chartData = (data?.monthly || []).map((m) => ({
    label: short(m.month_key),
    Gross: m.gross_cents / 100,
    Net: m.net_cents / 100,
    Super: m.super_cents / 100,
  }));

  return (
    <div data-testid="payroll-dashboard-page">
      <PageHeader
        title="Payroll"
        subtitle={`Australian payroll · ${fy || ""}`}
        children={
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1"
              onClick={scan} disabled={scanning} data-testid="scan-reminders-btn">
              <RefreshCw size={12} className={scanning ? "animate-spin" : ""} /> Scan reminders
            </Button>
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
          <div className="grid gap-2 md:grid-cols-4 mb-6" data-testid="payroll-kpis">
            <Kpi label="Active employees" value={data.active_employees} to="/payroll/employees" testId="kpi-employees" />
            <Kpi label="Draft pay runs" value={data.drafts_count} tone={data.drafts_count > 0 ? "warning" : "neutral"} to="/payroll/pay-runs" testId="kpi-drafts" />
            <Kpi label="Missing details" value={data.employees_missing_details} tone={data.employees_missing_details > 0 ? "warning" : "neutral"} testId="kpi-missing" hint="Bank / super / tax not configured" />
            <Kpi label="Pending leave" value={data.leave_pending_count} tone={data.leave_pending_count > 0 ? "warning" : "neutral"} to="/payroll/leave" testId="kpi-leave-pending" />
          </div>

          <div className="grid gap-2 md:grid-cols-4 mb-6" data-testid="payroll-ytd">
            <Kpi label={`YTD Gross (${data.fy})`} value={c(data.ytd?.gross_cents)} testId="kpi-ytd-gross" />
            <Kpi label="YTD Net" value={c(data.ytd?.net_cents)} testId="kpi-ytd-net" />
            <Kpi label="YTD Super (liability)" value={c(data.ytd?.super_cents)} testId="kpi-ytd-super" />
            <Kpi label="YTD Employer Cost" value={c(data.ytd?.total_employer_cost_cents)} testId="kpi-ytd-cost" />
          </div>

          <div className="grid gap-2 md:grid-cols-3 mb-6">
            <Kpi label="Super outstanding" value={c(data.super?.outstanding_cents)}
              tone={data.super?.outstanding_cents > 0 ? "warning" : "neutral"} to="/payroll/super" testId="kpi-super-out" />
            <Kpi label="Super OVERDUE" value={c(data.super?.overdue_cents)}
              tone={data.super?.overdue_cents > 0 ? "negative" : "neutral"} to="/payroll/super?status=accrued" testId="kpi-super-overdue" />
            <Kpi label="Leave liability (hours)" value={data.leave?.total_remaining_hours ?? "—"}
              to="/payroll/leave" testId="kpi-leave-hours" hint="Sum of remaining paid-leave hours across all employees." />
          </div>

          {chartData.length > 0 && (
            <Section title="Payroll trend by month" className="mb-6" testId="payroll-trend-chart">
              <div className="p-3">
                <MonthBarChart data={chartData}
                  keys={[
                    { key: "Gross", name: "Gross", color: "#0F291E" },
                    { key: "Net", name: "Net", color: "#166534" },
                    { key: "Super", name: "Super", color: "#B45309" },
                  ]}
                  height={240}
                />
              </div>
            </Section>
          )}

          {(data.super?.overdue_items || []).length > 0 && (
            <Section title="Overdue super — needs attention" className="mb-6" testId="overdue-super-section">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader><TableRow className="hover:bg-transparent">
                    {["Employee", "Quarter", "Due", "Outstanding", "Fund", ""].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
                  </TableRow></TableHeader>
                  <TableBody>
                    {data.super.overdue_items.map((it) => (
                      <TableRow key={it.liability_id} data-testid={`overdue-${it.liability_id}`}>
                        <TableCell className="text-xs">{it.employee_name}</TableCell>
                        <TableCell className="text-xs num">{it.quarter}</TableCell>
                        <TableCell className="text-xs num">{it.due_date}</TableCell>
                        <TableCell className="text-xs num text-right font-semibold text-negative">{c(it.outstanding_cents)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{it.fund_name || "—"}</TableCell>
                        <TableCell><Button asChild size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2">
                          <Link to="/payroll/super"><ArrowRight size={11} /></Link>
                        </Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Section>
          )}

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

      <div className="mt-4 flex gap-2 flex-wrap">
        <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
          <Link to="/payroll/reports" data-testid="go-payroll-reports"><FileText size={12} className="mr-1" /> Payroll Reports</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
          <Link to="/payroll/super" data-testid="go-super"><PiggyBank size={12} className="mr-1" /> Super Liabilities</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
          <Link to="/payroll/leave" data-testid="go-leave"><CalendarClock size={12} className="mr-1" /> Leave</Link>
        </Button>
        <Button asChild size="sm" variant="outline" className="rounded-sm text-xs">
          <Link to="/settings" data-testid="go-payroll-settings"><SettingsIcon size={12} className="mr-1" /> Payroll Settings</Link>
        </Button>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, tone = "neutral", to, testId, hint }) {
  const cls = tone === "positive" ? "text-positive" : tone === "warning" ? "text-warning"
             : tone === "negative" ? "text-negative" : "text-foreground";
  const inner = (
    <>
      <div className="overline">{label}</div>
      <div className={`num text-sm font-semibold mt-1 ${cls}`}>{value ?? "—"}</div>
      {hint && <div className="text-[10px] text-muted-foreground mt-1 leading-snug">{hint}</div>}
    </>
  );
  if (to) return <Link to={to} data-testid={testId} className={`border border-border p-3 bg-card hover:bg-accent/40 transition-colors ${tone === "warning" ? "bg-warning/5" : ""}`}>{inner}</Link>;
  return <div data-testid={testId} className={`border border-border p-3 bg-card ${tone === "warning" ? "bg-warning/5" : ""}`}>{inner}</div>;
}
