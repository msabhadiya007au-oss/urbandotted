import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtPct, errText } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, Delta, KpiCard, MonthBarChart, toChart, Pill,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TxnTable, TxnDetail } from "@/pages/Transactions";
import { ChevronRight, Plus, Archive, Pencil, ArrowLeft } from "lucide-react";

export default function Expenses() {
  const { fy, refreshKey, bump } = useApp();
  const [tree, setTree] = useState(null);
  const [totals, setTotals] = useState({});
  const [dialog, setDialog] = useState(null);
  const [name, setName] = useState("");
  const [parent, setParent] = useState(null);

  const load = () => {
    api.get("/categories?kind=expense").then(({ data }) => setTree(data.tree)).catch(() => setTree(false));
    api.get(`/reports/expense_by_category?fy=${fy}`).then(({ data }) => {
      const t = {};
      data.rows.forEach((r) => { t[r[0]] = (t[r[0]] || 0) + Number(r[5]); });
      setTotals(t);
    }).catch(() => {});
  };
  useEffect(() => { if (fy) load(); }, [fy, refreshKey]); // eslint-disable-line

  const save = async () => {
    try {
      await api.post("/categories", { name, parent_id: parent, kind: "expense" });
      toast.success("Category created");
      setDialog(null); setName(""); setParent(null);
      load(); bump();
    } catch (e) { toast.error(errText(e)); }
  };

  const archive = async (id) => {
    try { await api.post(`/categories/${id}/archive?archived=true`); toast.success("Category archived"); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!tree) return <Loading label="Loading categories" />;
  const grandTotal = Object.values(totals).reduce((a, b) => a + b, 0);

  return (
    <div data-testid="expenses-page">
      <PageHeader title="Expenses"
        subtitle="Unlimited categories and subcategories. Click any category to open its monthly detail page.">
        <Button size="sm" className="rounded-sm gap-1.5 bg-primary text-primary-foreground"
          onClick={() => { setParent(null); setDialog("category"); }} data-testid="add-category-btn">
          <Plus size={14} /> New category
        </Button>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-4 border border-border bg-border mb-6">
        <KpiCard label={`Total expenses ${fy?.replace("FY", "")}`} value={grandTotal} testId="kpi-expense-total" />
        <KpiCard label="Categories" value={String(tree.length)} testId="kpi-category-count" />
        <KpiCard label="Subcategories" value={String(tree.reduce((n, c) => n + c.children.length, 0))} testId="kpi-subcategory-count" />
        <KpiCard label="Largest category" value={Object.entries(totals).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"} testId="kpi-largest-category" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {tree.map((c) => (
          <Section key={c.category_id} testId={`category-card-${c.name}`}
            title={<span>{c.name}</span>}
            right={<span className="flex items-center gap-2">
              <Money value={totals[c.name] || 0} decimals={0} className="text-xs font-semibold" />
              <button onClick={() => archive(c.category_id)} data-testid={`archive-cat-${c.name}`}
                className="text-muted-foreground hover:text-negative transition-colors"><Archive size={12} /></button>
            </span>}>
            <div className="divide-y divide-border">
              <Link to={`/expenses/${c.category_id}`} data-testid={`open-category-${c.name}`}
                className="flex items-center justify-between px-4 py-2.5 text-sm hover:bg-accent/40 transition-colors group">
                <span className="font-semibold">All {c.name}</span>
                <ChevronRight size={14} className="opacity-40 group-hover:opacity-100" />
              </Link>
              {c.children.map((s) => (
                <Link key={s.category_id} to={`/expenses/${s.category_id}`} data-testid={`open-subcategory-${s.name}`}
                  className="flex items-center justify-between px-4 py-2 text-xs text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-colors group pl-7">
                  <span>{s.name}</span>
                  <ChevronRight size={12} className="opacity-0 group-hover:opacity-70" />
                </Link>
              ))}
              <button onClick={() => { setParent(c.category_id); setDialog("category"); }}
                data-testid={`add-sub-${c.name}`}
                className="w-full text-left px-4 py-2 pl-7 text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent/30 transition-colors">
                + Add subcategory
              </button>
            </div>
          </Section>
        ))}
      </div>

      {dialog && (
        <Dialog open onOpenChange={() => setDialog(null)}>
          <DialogContent className="bg-popover rounded-sm" data-testid="category-dialog">
            <DialogHeader><DialogTitle className="font-serif text-xl">
              {parent ? "New subcategory" : "New category"}
            </DialogTitle></DialogHeader>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Category name"
              className="rounded-sm" data-testid="category-name-input" />
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialog(null)} className="rounded-sm">Cancel</Button>
              <Button onClick={save} disabled={!name.trim()} className="rounded-sm bg-primary text-primary-foreground"
                data-testid="category-save-btn">Create</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export function CategoryDetail() {
  const { categoryId } = useParams();
  const { fy, refreshKey } = useApp();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (!fy) return;
    setData(null);
    api.get(`/categories/${categoryId}/detail?fy=${fy}`).then(({ data }) => setData(data)).catch(() => setData(false));
  }, [categoryId, fy, refreshKey]);

  if (!data) return <Loading label="Loading category" />;
  if (data === false) return <Empty title="Category not found" />;

  const chart = toChart(data.months, (m) => ({ Spend: m.amount }));

  return (
    <div data-testid="category-detail-page">
      <Link to="/expenses" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-3" data-testid="back-to-expenses">
        <ArrowLeft size={12} /> All expenses
      </Link>
      <PageHeader title={data.category.name}
        subtitle={`Every month of ${fy?.replace("FY", "")} for this ${data.category.parent_id ? "subcategory" : "category"}.`} />

      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-6">
        <KpiCard label={`Total ${fy?.replace("FY", "")}`} value={data.total} testId="cat-total" />
        <KpiCard label="GST recorded" value={data.total_gst} testId="cat-gst" />
        <KpiCard label="Average monthly" value={data.average_monthly} testId="cat-average" />
        <KpiCard label="Transactions" value={String(data.transaction_count)} testId="cat-count" />
        <KpiCard label="Months with activity" value={`${data.months_with_activity} / 12`} testId="cat-active-months" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Monthly spend" testId="cat-chart">
          <div className="p-3"><MonthBarChart data={chart} keys={[{ key: "Spend", name: "Spend", color: "#0F291E" }]} /></div>
        </Section>

        <Section title="Monthly table" testId="cat-monthly-table">
          <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                <TableHead className="overline">Month</TableHead>
                <TableHead className="overline text-right">Amount</TableHead>
                <TableHead className="overline text-right">GST</TableHead>
                <TableHead className="overline text-right">Txns</TableHead>
                <TableHead className="overline text-right">vs prev</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.months.map((m) => (
                  <TableRow key={m.month_key} data-testid={`cat-month-${m.month_key}`}>
                    <TableCell className="text-xs">{m.month_label}</TableCell>
                    <TableCell className="text-right"><Money value={m.amount} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={m.gst} className="text-xs text-muted-foreground" /></TableCell>
                    <TableCell className="text-right num text-xs">{m.count}</TableCell>
                    <TableCell className="text-right"><Delta value={m.change_pct} invert /></TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/40 font-semibold">
                  <TableCell className="text-xs">FY Total</TableCell>
                  <TableCell className="text-right"><Money value={data.total} className="text-xs font-semibold" /></TableCell>
                  <TableCell className="text-right"><Money value={data.total_gst} className="text-xs" /></TableCell>
                  <TableCell className="text-right num text-xs">{data.transaction_count}</TableCell>
                  <TableCell />
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </Section>
      </div>

      {data.subcategories?.length > 0 && (
        <Section title="Subcategories" className="mt-4" testId="cat-subcategories">
          <div className="divide-y divide-border">
            {data.subcategories.map((s) => (
              <Link key={s.category_id} to={`/expenses/${s.category_id}`} data-testid={`sub-link-${s.name}`}
                className="flex items-center justify-between px-4 py-2.5 text-sm hover:bg-accent/40 transition-colors group">
                <span>{s.name}</span>
                <span className="flex items-center gap-2">
                  <Money value={s.amount} decimals={0} className="text-xs" />
                  <ChevronRight size={13} className="opacity-30 group-hover:opacity-100" />
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      <Section title={`Transactions (${data.transactions.length})`} className="mt-4" testId="cat-transactions">
        {data.transactions.length === 0
          ? <Empty title="No transactions in this category yet" hint="Use + Add → Add Expense to record one." />
          : <TxnTable items={data.transactions} onRowClick={setSelected} />}
      </Section>

      {data.receipts?.length > 0 && (
        <Section title={`Receipts (${data.receipts.length})`} className="mt-4" testId="cat-receipts">
          <div className="p-4 flex flex-wrap gap-2">
            {data.receipts.map((d) => (
              <span key={d.document_id} className="text-xs border border-border px-2 py-1 rounded-sm num">{d.filename}</span>
            ))}
          </div>
        </Section>
      )}

      {data.notes?.length > 0 && (
        <Section title="Notes" className="mt-4" testId="cat-notes">
          <ul className="p-4 space-y-1.5 text-xs list-disc list-inside text-muted-foreground">
            {data.notes.slice(0, 20).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </Section>
      )}

      {selected && <TxnDetail txn={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
