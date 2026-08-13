import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtMoney, fmtPct, monthShort, fyLabel } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, KpiCard, Loading, MonthBarChart, MonthLineChart, BreakdownPie,
  Disclaimer, Money, Pill, toChart, StatRow,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertTriangle, ArrowRight } from "lucide-react";

const PERIODS = [
  { key: "fy", label: "Current FY" },
  { key: "month", label: "This Month" },
  { key: "quarter", label: "Quarter" },
];

export default function Dashboard() {
  const { fy, refreshKey } = useApp();
  const [data, setData] = useState(null);
  const [period, setPeriod] = useState("fy");
  const [reminders, setReminders] = useState([]);

  const nowKey = new Date().toISOString().slice(0, 7);
  useEffect(() => {
    if (!fy) return;
    setData(null);
    const params = new URLSearchParams({ fy, period });
    if (period !== "fy") params.set("month_key", nowKey);
    api.get(`/dashboard?${params}`).then(({ data }) => setData(data)).catch(() => setData(false));
    api.get(`/reminders?fy=${fy}&status=open`).then(({ data }) => setReminders(data.items.slice(0, 6))).catch(() => {});
  }, [fy, period, refreshKey]); // eslint-disable-line

  if (!data) return <Loading label="Building your dashboard" />;
  const k = data.kpis;
  const months = data.months || [];

  const revExp = toChart(months, (m) => ({ Revenue: m.net_sales, Expenses: m.operating_expenses, COGS: m.cogs }));
  const profit = toChart(months, (m) => ({ "Gross Profit": m.gross_profit, "Operating Profit": m.operating_profit }));
  const margin = toChart(months, (m) => ({ "Gross Margin %": m.gross_margin_pct ?? 0 }));
  const gst = toChart(months, (m) => ({ "GST Collected": m.gst_collected, "GST on Purchases": m.gst_paid }));
  const refundTrend = toChart(months, (m) => ({ Refunds: m.refunds }));
  const cogsTrend = toChart(months, (m) => ({ COGS: m.cogs }));
  const adSpend = (data.advertising_by_channel || []).slice(0, 6).map((c) => ({ name: c.name, amount: c.spend }));

  const attention = Object.entries(data.attention || {}).filter(([, v]) => v > 0);

  return (
    <div data-testid="dashboard-page">
      <PageHeader title="Dashboard"
        subtitle={`Financial year ${fy?.replace("FY", "")} · 1 July – 30 June · every figure below is clickable down to its source transactions.`}>
        <Tabs value={period} onValueChange={setPeriod}>
          <TabsList className="rounded-sm bg-muted h-9">
            {PERIODS.map((p) => (
              <TabsTrigger key={p.key} value={p.key} className="rounded-sm text-xs" data-testid={`period-${p.key}`}>
                {p.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </PageHeader>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 border border-border bg-border mb-4" data-testid="kpi-grid">
        <KpiCard label="Gross Sales" value={k.gross_sales} to="/sales" testId="kpi-gross-sales" />
        <KpiCard label="Net Sales" value={k.net_sales} to="/sales" testId="kpi-net-sales"
          sub={`less ${fmtMoney(k.discounts, 0)} discounts`} />
        <KpiCard label="Refunds" value={k.refunds} tone="negative" to="/refunds" testId="kpi-refunds"
          sub={`${fmtPct(k.refund_rate_pct)} refund rate`} />
        <KpiCard label="COGS" value={k.cogs} to="/cogs" testId="kpi-cogs" />
        <KpiCard label="Gross Profit" value={k.gross_profit} tone="positive" to="/reports/pnl" testId="kpi-gross-profit"
          sub={`${fmtPct(k.gross_margin_pct)} margin`} />
        <KpiCard label="Operating Expenses" value={k.operating_expenses} to="/expenses" testId="kpi-operating-expenses" />
        <KpiCard label="Operating Profit" value={k.operating_profit} tone={k.operating_profit >= 0 ? "positive" : "negative"}
          to="/reports/pnl" testId="kpi-operating-profit" sub={`${fmtPct(k.operating_margin_pct)} margin`} />
        <KpiCard label="GST Collected" value={k.gst_collected} to="/gst" testId="kpi-gst-collected" />
        <KpiCard label="GST Paid / Credits" value={k.gst_paid} to="/gst" testId="kpi-gst-paid"
          sub={`incl. ${fmtMoney(k.import_gst, 0)} import GST`} />
        <KpiCard label="Est. GST Position" value={k.estimated_gst_position} tone="warning" to="/gst"
          testId="kpi-gst-position" sub="Estimate only" />
        <KpiCard label="Cash Inflow" value={k.cash_inflow} to="/cashflow" testId="kpi-cash-inflow" />
        <KpiCard label="Cash Outflow" value={k.cash_outflow} to="/cashflow" testId="kpi-cash-outflow"
          sub={`net ${fmtMoney(k.net_cash_flow, 0)}`} />
      </div>

      <Disclaimer testId="dashboard-disclaimer">{data.disclaimer}</Disclaimer>

      {/* Attention */}
      {(attention.length > 0 || reminders.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2 mt-6">
          <Section title="Missing / To review" testId="attention-section"
            right={<Link to="/reminders" className="text-[11px] underline underline-offset-2">All reminders</Link>}>
            <div className="p-4 space-y-2">
              {reminders.length === 0 && <p className="text-xs text-muted-foreground">No missing recurring records detected.</p>}
              {reminders.map((r) => (
                <div key={r.reminder_id} className="flex items-start gap-2 text-xs" data-testid={`reminder-${r.reminder_id}`}>
                  <AlertTriangle size={13} className="text-warning mt-0.5 shrink-0" />
                  <span className="flex-1">{r.message}</span>
                  {r.expected_amount && <span className="num text-muted-foreground">~{fmtMoney(r.expected_amount, 0)}</span>}
                </div>
              ))}
            </div>
          </Section>

          <Section title="Data status" testId="data-status-section">
            <div className="p-4 grid grid-cols-2 gap-3">
              {[
                ["missing_receipts", "Missing receipts", "/documents/missing"],
                ["uncategorised", "Uncategorised", "/transactions?uncategorised=1"],
                ["needs_review", "Needs review", "/transactions?needs_review=1"],
                ["unreconciled", "Unreconciled", "/transactions?reconcile_status=unreconciled"],
                ["ask_accountant", "Ask accountant", "/transactions?ask_accountant=1"],
                ["open_reminders", "Open reminders", "/reminders"],
              ].map(([key, label, to]) => (
                <Link key={key} to={to} data-testid={`status-${key}`}
                  className="flex items-center justify-between gap-2 border border-border px-3 py-2 lift hover:bg-accent/40">
                  <span className="text-[11px] text-muted-foreground">{label}</span>
                  <span className="num text-sm font-semibold">{data.attention[key] ?? 0}</span>
                </Link>
              ))}
            </div>
          </Section>
        </div>
      )}

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2 mt-6">
        <Section title="Revenue vs Expenses" testId="chart-revenue-expenses">
          <div className="p-3"><MonthBarChart data={revExp} keys={[
            { key: "Revenue", name: "Net sales", color: "#166534" },
            { key: "COGS", name: "COGS", color: "#B45309" },
            { key: "Expenses", name: "Operating expenses", color: "#9F1239" }]} /></div>
        </Section>
        <Section title="Profit by Month" testId="chart-profit">
          <div className="p-3"><MonthBarChart data={profit} keys={[
            { key: "Gross Profit", name: "Gross profit", color: "#0F291E" },
            { key: "Operating Profit", name: "Operating profit", color: "#166534" }]} /></div>
        </Section>
        <Section title="Gross Margin %" testId="chart-margin">
          <div className="p-3"><MonthLineChart data={margin} keys={[{ key: "Gross Margin %", name: "Gross margin %", color: "#0F291E" }]} /></div>
        </Section>
        <Section title="Advertising Spend by Channel" testId="chart-advertising"
          right={<Link to="/advertising" className="text-[11px] underline underline-offset-2">Advertising</Link>}>
          <div className="p-3">
            {adSpend.length ? <BreakdownPie data={adSpend} /> :
              <p className="text-xs text-muted-foreground p-6 text-center">No advertising recorded yet.</p>}
          </div>
        </Section>
        <Section title="Refund Trend" testId="chart-refunds">
          <div className="p-3"><MonthBarChart data={refundTrend} keys={[{ key: "Refunds", name: "Refunds", color: "#9F1239" }]} /></div>
        </Section>
        <Section title="COGS Trend" testId="chart-cogs">
          <div className="p-3"><MonthLineChart data={cogsTrend} keys={[{ key: "COGS", name: "COGS", color: "#B45309" }]} /></div>
        </Section>
        <Section title="Monthly GST" testId="chart-gst">
          <div className="p-3"><MonthBarChart data={gst} keys={[
            { key: "GST Collected", name: "Collected", color: "#0F291E" },
            { key: "GST on Purchases", name: "On purchases", color: "#2F5F73" }]} /></div>
        </Section>
        <Section title="Top Expense Categories" testId="chart-top-categories"
          right={<Link to="/expenses" className="text-[11px] underline underline-offset-2">All expenses</Link>}>
          <div className="divide-y divide-border">
            {(data.top_expense_categories || []).map((c) => (
              <Link key={c.category_id || c.name} to={c.category_id ? `/expenses/${c.category_id}` : "/transactions?uncategorised=1"}
                data-testid={`top-cat-${c.name}`}
                className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-accent/40 transition-colors group">
                <span className="text-sm">{c.name}</span>
                <span className="flex items-center gap-2">
                  <Money value={c.amount} decimals={0} className="text-sm" />
                  <ArrowRight size={12} className="opacity-0 group-hover:opacity-60 transition-opacity" />
                </span>
              </Link>
            ))}
            {!data.top_expense_categories?.length && <p className="text-xs text-muted-foreground p-6 text-center">No expenses yet.</p>}
          </div>
        </Section>
      </div>

      {/* Profit calculation transparency */}
      <Section title="How operating profit was calculated" className="mt-6" testId="profit-breakdown">
        <div className="p-4 grid gap-6 md:grid-cols-2">
          <div>
            <StatRow label="Gross Sales" value={k.gross_sales} />
            <StatRow label="less Discounts" value={-k.discounts} indent tone="negative" />
            <StatRow label="less Refunds" value={-k.refunds} indent tone="negative" />
            <StatRow label="= Net Sales" value={k.net_sales} bold formula="Gross Sales − Discounts − Refunds" />
            <StatRow label="less COGS" value={-k.cogs} indent tone="negative" />
            <StatRow label="= Gross Profit" value={k.gross_profit} bold tone="positive" formula="Net Sales − COGS" />
          </div>
          <div>
            <StatRow label="Gross Profit" value={k.gross_profit} />
            <StatRow label="less Operating Expenses" value={-k.operating_expenses} indent tone="negative" />
            <StatRow label="= Operating Profit" value={k.operating_profit} bold
              tone={k.operating_profit >= 0 ? "positive" : "negative"} formula="Gross Profit − Operating Expenses" />
            <div className="flex flex-wrap gap-2 mt-4">
              <Pill>Gross margin {fmtPct(k.gross_margin_pct)}</Pill>
              <Pill>Operating margin {fmtPct(k.operating_margin_pct)}</Pill>
              <Pill tone="negative">Refund rate {fmtPct(k.refund_rate_pct)}</Pill>
              <Pill tone="warning">Ads {fmtPct(k.advertising_pct_of_net_sales)} of net sales</Pill>
            </div>
            <Button asChild variant="outline" size="sm" className="rounded-sm mt-4" data-testid="view-pnl-btn">
              <Link to="/reports/pnl">Open full Profit &amp; Loss</Link>
            </Button>
          </div>
        </div>
      </Section>
    </div>
  );
}
