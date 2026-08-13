import React from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, ArrowDownRight, Minus, Loader2 } from "lucide-react";
import { fmtMoney, fmtPct, monthShort } from "@/lib/api";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";

export const CHART_COLORS = ["#0F291E", "#166534", "#9F1239", "#B45309", "#2F5F73", "#6B7280", "#4C1D95"];

export function PageHeader({ title, subtitle, children, testId }) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between mb-8" data-testid={testId}>
      <div>
        <h1 className="font-serif text-3xl sm:text-4xl font-semibold text-foreground">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function Section({ title, right, children, className = "", testId }) {
  return (
    <section className={`grid-card ${className}`} data-testid={testId}>
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border">
          <h2 className="overline">{title}</h2>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Delta({ value, invert = false }) {
  if (value === null || value === undefined) {
    return <span className="num text-xs text-muted-foreground inline-flex items-center gap-1"><Minus size={11} />—</span>;
  }
  const good = invert ? value < 0 : value > 0;
  const flat = Math.abs(value) < 0.005;
  const Icon = value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className={`num text-xs inline-flex items-center gap-0.5 ${flat ? "text-muted-foreground" : good ? "text-positive" : "text-negative"}`}>
      {!flat && <Icon size={12} />}
      {value > 0 ? "+" : ""}{Number(value).toFixed(1)}%
    </span>
  );
}

export function KpiCard({ label, value, sub, delta, tone = "neutral", to, testId, decimals = 0 }) {
  const toneClass = tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative"
    : tone === "warning" ? "text-warning" : "text-foreground";
  const inner = (
    <>
      <div className="overline">{label}</div>
      <div className={`num text-xl lg:text-2xl font-semibold mt-2 ${toneClass}`}>
        {typeof value === "number" ? fmtMoney(value, decimals) : value}
      </div>
      <div className="flex items-center gap-2 mt-1.5 min-h-[18px]">
        {delta !== undefined && <Delta value={delta} />}
        {sub && <span className="text-[11px] text-muted-foreground truncate">{sub}</span>}
      </div>
    </>
  );
  if (to) {
    return (
      <Link to={to} data-testid={testId}
        className="block bg-card p-4 -ml-px -mt-px border border-border lift hover:bg-accent/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        {inner}
      </Link>
    );
  }
  return <div data-testid={testId} className="bg-card p-4 -ml-px -mt-px border border-border">{inner}</div>;
}

export function Money({ value, decimals = 2, className = "", signed = false }) {
  const n = Number(value ?? 0);
  const tone = signed ? (n > 0 ? "text-positive" : n < 0 ? "text-negative" : "") : "";
  return <span className={`num ${tone} ${className}`}>{signed && n > 0 ? "+" : ""}{fmtMoney(n, decimals)}</span>;
}

export function Loading({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center py-24 text-muted-foreground gap-2" data-testid="loading-state">
      <Loader2 className="animate-spin" size={16} />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function Empty({ title = "No records yet", hint, action }) {
  return (
    <div className="text-center py-16 px-6" data-testid="empty-state">
      <p className="font-serif text-xl text-foreground">{title}</p>
      {hint && <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Disclaimer({ children, testId }) {
  return (
    <p className="text-[11px] leading-relaxed text-muted-foreground border-l-2 border-warning/60 pl-3 py-1" data-testid={testId}>
      {children}
    </p>
  );
}

export function Phase({ phase }) {
  return (
    <span className="inline-flex items-center text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 border border-warning/40 text-warning bg-warning/5 rounded-sm">
      {phase}
    </span>
  );
}

const axisProps = {
  tick: { fontSize: 10, fill: "#64748B", fontFamily: "JetBrains Mono" },
  stroke: "#E5E2DC",
};
const tooltipStyle = {
  contentStyle: {
    background: "#FFFFFF", border: "1px solid #E5E2DC", borderRadius: 2,
    fontSize: 11, fontFamily: "Manrope", boxShadow: "none",
  },
  formatter: (v, n) => [fmtMoney(v), n],
};

export function MonthBarChart({ data, keys, height = 260, stacked = false }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#EFEDE6" vertical={false} />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={58} tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
        <Tooltip {...tooltipStyle} />
        {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {keys.map((k, i) => (
          <Bar key={k.key} dataKey={k.key} name={k.name} stackId={stacked ? "a" : undefined}
            fill={k.color || CHART_COLORS[i % CHART_COLORS.length]} radius={[1, 1, 0, 0]} maxBarSize={34} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MonthLineChart({ data, keys, height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#EFEDE6" vertical={false} />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={58} tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
        <Tooltip {...tooltipStyle} />
        {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {keys.map((k, i) => (
          <Line key={k.key} type="monotone" dataKey={k.key} name={k.name} dot={false} strokeWidth={2}
            stroke={k.color || CHART_COLORS[i % CHART_COLORS.length]} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function MonthAreaChart({ data, keys, height = 240 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#EFEDE6" vertical={false} />
        <XAxis dataKey="label" {...axisProps} />
        <YAxis {...axisProps} width={58} tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
        <Tooltip {...tooltipStyle} />
        {keys.map((k, i) => (
          <Area key={k.key} type="monotone" dataKey={k.key} name={k.name} strokeWidth={2}
            stroke={k.color || CHART_COLORS[i % CHART_COLORS.length]}
            fill={k.color || CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.08} />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function BreakdownPie({ data, height = 260, nameKey = "name", dataKey = "amount" }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={data} dataKey={dataKey} nameKey={nameKey} innerRadius="52%" outerRadius="80%"
          paddingAngle={1} stroke="#FFFFFF" strokeWidth={1}>
          {data.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
        </Pie>
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export const toChart = (months, mapper) =>
  (months || []).map((m) => ({ label: monthShort(m.month_key), month_key: m.month_key, ...mapper(m) }));

export function StatRow({ label, value, bold, indent, tone, formula }) {
  return (
    <div className={`flex items-baseline justify-between gap-4 py-2 border-b border-border/60 last:border-0 ${indent ? "pl-4" : ""}`}>
      <span className={`text-sm ${bold ? "font-semibold text-foreground" : "text-muted-foreground"}`}>
        {label}
        {formula && <span className="block text-[10px] text-muted-foreground/70 num">{formula}</span>}
      </span>
      <span className={`num text-sm ${bold ? "font-semibold" : ""} ${tone === "negative" ? "text-negative" : tone === "positive" ? "text-positive" : ""}`}>
        {typeof value === "number" ? fmtMoney(value) : value}
      </span>
    </div>
  );
}

export function Pill({ children, tone = "neutral", testId }) {
  const map = {
    neutral: "border-border text-muted-foreground bg-muted/50",
    positive: "border-positive/30 text-positive bg-positive/5",
    negative: "border-negative/30 text-negative bg-negative/5",
    warning: "border-warning/40 text-warning bg-warning/5",
  };
  return (
    <span data-testid={testId}
      className={`inline-flex items-center text-[10px] uppercase tracking-wider font-semibold px-1.5 py-0.5 border rounded-sm whitespace-nowrap ${map[tone]}`}>
      {children}
    </span>
  );
}

export { fmtPct };
