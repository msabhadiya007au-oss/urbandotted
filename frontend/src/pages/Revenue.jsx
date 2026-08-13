import React, { useEffect, useState } from "react";
import { api, fmtMoney, fmtPct, fmtNum } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, KpiCard, MonthBarChart, MonthLineChart,
  BreakdownPie, toChart, Pill, Disclaimer, StatRow,
} from "@/components/shared";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TxnTable, TxnDetail } from "@/pages/Transactions";

export function Sales() {
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/sales/summary?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);
  if (!d) return <Loading label="Loading revenue" />;
  const t = d.totals;
  const chart = toChart(d.months, (m) => ({ "Gross sales": m.gross_sales, "Net sales": m.net_sales, Refunds: m.refunds }));

  return (
    <div data-testid="sales-page">
      <PageHeader title="Sales &amp; Revenue"
        subtitle="Manual entry now; the data model already stores external IDs so Shopify orders can sync without duplicates.">
        <Pill tone="warning">Shopify sync — Coming in Phase 4</Pill>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 border border-border bg-border mb-4">
        <KpiCard label="Gross Sales" value={t.gross_sales} testId="sales-gross" />
        <KpiCard label="Discounts" value={t.discounts} tone="negative" testId="sales-discounts" />
        <KpiCard label="Refunds" value={t.refunds} tone="negative" to="/refunds" testId="sales-refunds" />
        <KpiCard label="Net Sales" value={t.net_sales} tone="positive" testId="sales-net" />
        <KpiCard label="Shipping Revenue" value={t.shipping_revenue} testId="sales-shipping" />
        <KpiCard label="Taxes Collected" value={t.taxes_collected} to="/gst" testId="sales-taxes" />
        <KpiCard label="Gateway Fees" value={t.payment_gateway_fees} testId="sales-fees" />
        <KpiCard label="Gift Cards" value={t.gift_cards} testId="sales-gift-cards" />
        <KpiCard label="Other Income" value={t.other_income} testId="sales-other-income" />
        <KpiCard label="Sales Records" value={fmtNum(t.order_count)} testId="sales-count" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Revenue by month" testId="sales-chart">
          <div className="p-3"><MonthBarChart data={chart} keys={[
            { key: "Gross sales", name: "Gross", color: "#0F291E" },
            { key: "Net sales", name: "Net", color: "#166534" },
            { key: "Refunds", name: "Refunds", color: "#9F1239" }]} /></div>
        </Section>
        <Section title="Net sales derivation" testId="sales-derivation">
          <div className="p-4">
            <StatRow label="Gross Sales" value={t.gross_sales} />
            <StatRow label="less Discounts" value={-t.discounts} indent tone="negative" />
            <StatRow label="less Refunds" value={-t.refunds} indent tone="negative" />
            <StatRow label="= Net Sales" value={t.net_sales} bold tone="positive" formula="Gross − Discounts − Refunds" />
            <p className="text-[11px] text-muted-foreground mt-3">{d.shopify_status}</p>
          </div>
        </Section>
      </div>

      <Section title="Monthly table" className="mt-4" testId="sales-monthly-table">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Month", "Gross Sales", "Discounts", "Refunds", "Net Sales", "Shipping Revenue", "Gateway Fees"].map((h, i) => (
                <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {d.months.map((m) => (
                <TableRow key={m.month_key} data-testid={`sales-month-${m.month_key}`}>
                  <TableCell className="text-xs">{m.month_label}</TableCell>
                  {["gross_sales", "discounts", "refunds", "net_sales", "shipping_revenue", "fees"].map((k) => (
                    <TableCell key={k} className="text-right"><Money value={m[k]} className="text-xs" /></TableCell>))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      <Section title={`Sales records (${d.transactions.length})`} className="mt-4" testId="sales-transactions">
        {d.transactions.length === 0 ? <Empty title="No sales recorded" hint="+ Add → Add Sale" />
          : <TxnTable items={d.transactions} onRowClick={setSel} />}
      </Section>
      {sel && <TxnDetail txn={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

export function Refunds() {
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/refunds/analytics?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);
  if (!d) return <Loading label="Loading refunds" />;
  const t = d.totals;

  return (
    <div data-testid="refunds-page">
      <PageHeader title="Refunds" subtitle="Refund totals, rate, reasons and products for the selected financial year." />
      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-4">
        <KpiCard label="Total Refunds" value={t.refunds} tone="negative" testId="refund-total" />
        <KpiCard label="Refund Count" value={fmtNum(t.count)} testId="refund-count" />
        <KpiCard label="Refund Rate" value={fmtPct(t.refund_rate_pct)} testId="refund-rate" sub="of gross sales" />
        <KpiCard label="GST on Refunds" value={t.gst_on_refunds} testId="refund-gst" />
        <KpiCard label="Gross Sales" value={t.gross_sales} testId="refund-gross-sales" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Refunds by month" testId="refund-chart">
          <div className="p-3"><MonthBarChart data={toChart(d.months, (m) => ({ Refunds: m.amount }))}
            keys={[{ key: "Refunds", name: "Refunds", color: "#9F1239" }]} /></div>
        </Section>
        <Section title="Refund reasons" testId="refund-reasons">
          <div className="p-3">
            {d.by_reason.length ? <BreakdownPie data={d.by_reason.map((r) => ({ name: r.reason, amount: r.amount }))} />
              : <p className="text-xs text-muted-foreground p-6 text-center">No refunds recorded.</p>}
          </div>
        </Section>
      </div>

      <Section title="Refunds by product" className="mt-4" testId="refund-by-product">
        <div className="divide-y divide-border">
          {d.by_product.map((p) => (
            <div key={p.sku} className="flex justify-between px-4 py-2 text-xs">
              <span className="num">{p.sku}</span><Money value={p.amount} className="text-xs" />
            </div>
          ))}
          {!d.by_product.length && <p className="text-xs text-muted-foreground p-6 text-center">No product-level refunds.</p>}
        </div>
      </Section>

      <Section title={`Refund transactions (${d.transactions.length})`} className="mt-4" testId="refund-transactions">
        {d.transactions.length === 0 ? <Empty title="No refunds recorded" hint="+ Add → Add Refund" />
          : <TxnTable items={d.transactions} onRowClick={setSel} />}
      </Section>
      {sel && <TxnDetail txn={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

export function Advertising() {
  const { fy, refreshKey } = useApp();
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/advertising?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);
  if (!d) return <Loading label="Loading advertising" />;

  return (
    <div data-testid="advertising-page">
      <PageHeader title="Advertising" subtitle="Spend by channel with derived performance metrics — calculated only where you have entered the inputs.">
        <Pill tone="warning">Ad platform APIs — Coming in Phase 5</Pill>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-4 border border-border bg-border mb-4">
        <KpiCard label={`FY Ad Spend ${fy?.replace("FY", "")}`} value={d.totals.spend} testId="ad-total" />
        <KpiCard label="Channels" value={String(d.channels.length)} testId="ad-channels" />
        <KpiCard label="Top Channel" value={d.channels[0]?.name || "—"} testId="ad-top-channel" />
        <KpiCard label="Top Channel Spend" value={d.channels[0]?.spend || 0} testId="ad-top-spend" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Monthly ad spend" testId="ad-chart">
          <div className="p-3"><MonthBarChart data={toChart(d.months, (m) => ({ Spend: m.amount }))}
            keys={[{ key: "Spend", name: "Ad spend", color: "#B45309" }]} /></div>
        </Section>
        <Section title="Share of ad spend" testId="ad-share">
          <div className="p-3">
            {d.channels.length ? <BreakdownPie data={d.channels.map((c) => ({ name: c.name, amount: c.spend }))} />
              : <p className="text-xs text-muted-foreground p-6 text-center">No advertising recorded.</p>}
          </div>
        </Section>
      </div>

      <Section title="Channel performance" className="mt-4" testId="ad-channel-table">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Channel", "FY Spend", "% of Ad Spend", "Revenue Attributed", "Orders", "Clicks", "Impressions", "ROAS", "CPA", "CPC", "CTR"].map((h, i) => (
                <TableHead key={h} className={`overline ${i ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {d.channels.map((c) => (
                <TableRow key={c.name} data-testid={`ad-channel-${c.name}`}>
                  <TableCell className="text-xs">{c.name}</TableCell>
                  <TableCell className="text-right"><Money value={c.spend} className="text-xs" /></TableCell>
                  <TableCell className="text-right num text-xs">{fmtPct(c.pct_of_total_ad_spend)}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.revenue_attributed !== null ? fmtMoney(c.metrics.revenue_attributed) : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.orders ?? "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.clicks !== null ? fmtNum(c.metrics.clicks) : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.impressions !== null ? fmtNum(c.metrics.impressions) : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.roas !== null ? `${c.metrics.roas}x` : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.cpa !== null ? fmtMoney(c.metrics.cpa) : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.cpc !== null ? fmtMoney(c.metrics.cpc) : "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{c.metrics.ctr !== null ? fmtPct(c.metrics.ctr) : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        <div className="p-4 border-t border-border"><Disclaimer>{d.note}</Disclaimer></div>
      </Section>

      <div className="grid gap-4 lg:grid-cols-2 mt-4">
        {d.channels.slice(0, 4).map((c) => (
          <Section key={c.name} title={`${c.name} — monthly`} testId={`ad-monthly-${c.name}`}>
            <div className="p-3"><MonthLineChart height={200}
              data={toChart(c.months, (m) => ({ Spend: m.amount }))}
              keys={[{ key: "Spend", name: c.name, color: "#0F291E" }]} /></div>
          </Section>
        ))}
      </div>
    </div>
  );
}
