import React, { useEffect, useState, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtDate, errText, GST_LABELS, TXN_TYPE_LABELS, downloadFile } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Money, Pill } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { useLookups } from "@/components/QuickAdd";
import QuickAdd from "@/components/QuickAdd";
import { Download, Trash2, Tag, CheckCircle2, FolderTree, Upload, Pencil, MessageCircleQuestion } from "lucide-react";

const ANY = "__any__";

export function TxnTable({ items, onSelect, selected = [], onRowClick }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {onSelect && <TableHead className="w-8" />}
            <TableHead className="overline">Date</TableHead>
            <TableHead className="overline">Type</TableHead>
            <TableHead className="overline">Category</TableHead>
            <TableHead className="overline">Supplier</TableHead>
            <TableHead className="overline">Description</TableHead>
            <TableHead className="overline text-right">Ex GST</TableHead>
            <TableHead className="overline text-right">GST</TableHead>
            <TableHead className="overline text-right">Inc GST</TableHead>
            <TableHead className="overline">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((t) => (
            <TableRow key={t.txn_id} data-testid={`txn-row-${t.txn_id}`}
              className="cursor-pointer" onClick={() => onRowClick?.(t)}>
              {onSelect && (
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox checked={selected.includes(t.txn_id)} onCheckedChange={() => onSelect(t.txn_id)}
                    data-testid={`txn-select-${t.txn_id}`} />
                </TableCell>
              )}
              <TableCell className="num text-xs whitespace-nowrap">{fmtDate(t.date)}</TableCell>
              <TableCell className="text-xs">{TXN_TYPE_LABELS[t.txn_type]}</TableCell>
              <TableCell className="text-xs">
                {t.category_id ? (
                  <Link to={`/expenses/${t.subcategory_id || t.category_id}`} onClick={(e) => e.stopPropagation()}
                    className="underline underline-offset-2 decoration-border hover:decoration-foreground">
                    {t.subcategory_name || t.category_name}
                  </Link>
                ) : <Pill tone="warning">Uncategorised</Pill>}
              </TableCell>
              <TableCell className="text-xs">{t.supplier_name || "—"}</TableCell>
              <TableCell className="text-xs max-w-[240px] truncate">{t.description || "—"}</TableCell>
              <TableCell className="text-right"><Money value={t.amount_ex} className="text-xs" /></TableCell>
              <TableCell className="text-right"><Money value={t.gst} className="text-xs text-muted-foreground" /></TableCell>
              <TableCell className="text-right"><Money value={t.amount_inc} className="text-xs font-semibold" /></TableCell>
              <TableCell>
                <div className="flex flex-wrap gap-1">
                  {!t.has_receipt && t.txn_type === "expense" && <Pill tone="warning">No receipt</Pill>}
                  {t.gst_treatment === "unknown" && <Pill tone="warning">GST ?</Pill>}
                  {t.ask_accountant && <Pill tone="negative">Ask accountant</Pill>}
                  {t.reconcile_status === "reconciled" && <Pill tone="positive">Reconciled</Pill>}
                  {t.is_demo && <Pill>Demo</Pill>}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function Transactions() {
  const { fy, refreshKey, bump } = useApp();
  const [sp, setSp] = useSearchParams();
  const lk = useLookups();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState([]);
  const [bulk, setBulk] = useState(null);
  const [editing, setEditing] = useState(null);
  const [f, setF] = useState({
    q: sp.get("q") || "", txn_type: sp.get("txn_type") || ANY, category_id: sp.get("category_id") || ANY,
    supplier_id: ANY, account_id: ANY, gst_treatment: ANY, receipt_status: sp.get("receipt_status") || ANY,
    reconcile_status: sp.get("reconcile_status") || ANY, month_key: ANY, tag: "",
    amount_min: "", amount_max: "", date_from: "", date_to: "",
    uncategorised: sp.get("uncategorised") === "1", needs_review: sp.get("needs_review") === "1",
    ask_accountant: sp.get("ask_accountant") === "1",
  });
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const params = useMemo(() => {
    const p = new URLSearchParams({ fy, limit: "500" });
    Object.entries(f).forEach(([k, v]) => {
      if (v === "" || v === ANY || v === false) return;
      p.set(k, v === true ? "true" : v);
    });
    return p.toString();
  }, [f, fy]);

  useEffect(() => {
    if (!fy) return;
    setData(null);
    api.get(`/transactions?${params}`).then(({ data }) => setData(data)).catch(() => setData(false));
  }, [params, fy, refreshKey]);

  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const runBulk = async (action, extra = {}) => {
    try {
      const { data: r } = await api.post("/transactions/bulk", { txn_ids: selected, action, ...extra });
      toast.success(`${r.affected} transaction(s) updated`);
      setSelected([]);
      setBulk(null);
      bump();
    } catch (e) { toast.error(errText(e)); }
  };

  const monthOpts = data?.items ? [...new Set(data.items.map((t) => t.month_key))].sort() : [];

  return (
    <div data-testid="transactions-page">
      <PageHeader title="Transactions" subtitle="Every expense, sale, refund and other income record with full filtering and bulk actions.">
        <Button variant="outline" size="sm" className="rounded-sm gap-1.5" data-testid="export-transactions-btn"
          onClick={() => downloadFile(`/export/transactions?fy=${fy}`, `transactions_${fy}.csv`)}>
          <Download size={14} /> Export CSV
        </Button>
        <Button asChild variant="outline" size="sm" className="rounded-sm gap-1.5" data-testid="import-link">
          <Link to="/import"><Upload size={14} /> Import CSV</Link>
        </Button>
      </PageHeader>

      <Section title="Filters" testId="filters-section">
        <div className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input placeholder="Search description, supplier, reference…" value={f.q}
            onChange={(e) => set("q")(e.target.value)} className="rounded-sm text-sm" data-testid="filter-q" />
          <Select value={f.txn_type} onValueChange={set("txn_type")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-type"><SelectValue placeholder="Type" /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value={ANY}>All types</SelectItem>
              {Object.entries(TXN_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={f.category_id} onValueChange={set("category_id")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-category"><SelectValue placeholder="Category" /></SelectTrigger>
            <SelectContent className="bg-popover max-h-72">
              <SelectItem value={ANY}>All categories</SelectItem>
              {lk.flat.filter((c) => !c.parent_id).map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={f.supplier_id} onValueChange={set("supplier_id")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-supplier"><SelectValue placeholder="Supplier" /></SelectTrigger>
            <SelectContent className="bg-popover max-h-72">
              <SelectItem value={ANY}>All suppliers</SelectItem>
              {lk.suppliers.map((s) => <SelectItem key={s.supplier_id} value={s.supplier_id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={f.gst_treatment} onValueChange={set("gst_treatment")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-gst"><SelectValue placeholder="GST status" /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value={ANY}>Any GST status</SelectItem>
              {Object.entries(GST_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={f.receipt_status} onValueChange={set("receipt_status")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-receipt"><SelectValue placeholder="Receipt" /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value={ANY}>Any receipt status</SelectItem>
              <SelectItem value="attached">Receipt attached</SelectItem>
              <SelectItem value="missing">Receipt missing</SelectItem>
            </SelectContent>
          </Select>
          <Select value={f.reconcile_status} onValueChange={set("reconcile_status")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-reconcile"><SelectValue placeholder="Reconciliation" /></SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value={ANY}>Any reconciliation</SelectItem>
              {["unreconciled", "matched", "reconciled", "needs_review"].map((s) =>
                <SelectItem key={s} value={s} className="capitalize">{s.replace("_", " ")}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={f.month_key} onValueChange={set("month_key")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="filter-month"><SelectValue placeholder="Month" /></SelectTrigger>
            <SelectContent className="bg-popover max-h-72">
              <SelectItem value={ANY}>All months</SelectItem>
              {monthOpts.map((m) => <SelectItem key={m} value={m} className="num">{m}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input type="number" placeholder="Min amount" value={f.amount_min} onChange={(e) => set("amount_min")(e.target.value)}
            className="rounded-sm num text-xs" data-testid="filter-amount-min" />
          <Input type="number" placeholder="Max amount" value={f.amount_max} onChange={(e) => set("amount_max")(e.target.value)}
            className="rounded-sm num text-xs" data-testid="filter-amount-max" />
          <Input type="date" value={f.date_from} onChange={(e) => set("date_from")(e.target.value)}
            className="rounded-sm num text-xs" data-testid="filter-date-from" />
          <Input type="date" value={f.date_to} onChange={(e) => set("date_to")(e.target.value)}
            className="rounded-sm num text-xs" data-testid="filter-date-to" />
          <Input placeholder="Tag" value={f.tag} onChange={(e) => set("tag")(e.target.value)}
            className="rounded-sm text-xs" data-testid="filter-tag" />
          <div className="flex items-center gap-4 col-span-full flex-wrap">
            {[["uncategorised", "Uncategorised only"], ["needs_review", "Needs review"], ["ask_accountant", "Ask accountant"]].map(([k, l]) => (
              <label key={k} className="flex items-center gap-2 text-xs cursor-pointer">
                <Checkbox checked={f[k]} onCheckedChange={(v) => set(k)(!!v)} data-testid={`filter-${k}`} /> {l}
              </label>
            ))}
            <Button variant="ghost" size="sm" className="rounded-sm text-xs ml-auto" data-testid="clear-filters"
              onClick={() => setF({ q: "", txn_type: ANY, category_id: ANY, supplier_id: ANY, account_id: ANY,
                gst_treatment: ANY, receipt_status: ANY, reconcile_status: ANY, month_key: ANY, tag: "",
                amount_min: "", amount_max: "", date_from: "", date_to: "", uncategorised: false,
                needs_review: false, ask_accountant: false })}>
              Clear filters
            </Button>
          </div>
        </div>
      </Section>

      {selected.length > 0 && (
        <div className="mt-4 grid-card p-3 flex flex-wrap items-center gap-2" data-testid="bulk-bar">
          <span className="num text-xs font-semibold mr-2">{selected.length} selected</span>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs" onClick={() => setBulk("category")} data-testid="bulk-category">
            <FolderTree size={13} /> Change category
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs" onClick={() => setBulk("gst")} data-testid="bulk-gst">
            GST treatment
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs" onClick={() => setBulk("tag")} data-testid="bulk-tag">
            <Tag size={13} /> Add tag
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs" onClick={() => runBulk("mark_reviewed")} data-testid="bulk-reviewed">
            <CheckCircle2 size={13} /> Mark reviewed
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs"
            onClick={() => runBulk("reconcile", { reconcile_status: "reconciled" })} data-testid="bulk-reconcile">
            Reconcile
          </Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-xs text-negative" onClick={() => runBulk("delete")} data-testid="bulk-delete">
            <Trash2 size={13} /> Archive
          </Button>
        </div>
      )}

      <Section className="mt-4" testId="transactions-table-section"
        title={data ? `${data.total} transactions` : "Transactions"}
        right={data && (
          <span className="num text-xs text-muted-foreground">
            Ex {fmtMoney(data.totals.amount_ex)} · GST {fmtMoney(data.totals.gst)} · Inc {fmtMoney(data.totals.amount_inc)}
          </span>
        )}>
        {!data ? <Loading /> : data.items.length === 0
          ? <Empty title="No transactions match these filters" hint="Adjust the filters, or use the + Add button to record one." />
          : <TxnTable items={data.items} onSelect={toggle} selected={selected} onRowClick={setEditing} />}
      </Section>

      {bulk && <BulkDialog kind={bulk} lk={lk} onClose={() => setBulk(null)} onApply={runBulk} />}
      {editing && <TxnDetail txn={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function BulkDialog({ kind, lk, onClose, onApply }) {
  const [v, setV] = useState("");
  const [sub, setSub] = useState(ANY);
  const parents = lk.flat.filter((c) => !c.parent_id);
  const subs = lk.flat.filter((c) => c.parent_id === v);
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="bg-popover rounded-sm" data-testid="bulk-dialog">
        <DialogHeader><DialogTitle className="font-serif text-xl">
          {kind === "category" ? "Change category" : kind === "gst" ? "Change GST treatment" : "Add tag"}
        </DialogTitle></DialogHeader>
        {kind === "category" && (
          <div className="space-y-3">
            <Select value={v} onValueChange={(x) => { setV(x); setSub(ANY); }}>
              <SelectTrigger className="rounded-sm" data-testid="bulk-category-select"><SelectValue placeholder="Category" /></SelectTrigger>
              <SelectContent className="bg-popover max-h-72">
                {parents.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
            {subs.length > 0 && (
              <Select value={sub} onValueChange={setSub}>
                <SelectTrigger className="rounded-sm" data-testid="bulk-subcategory-select"><SelectValue placeholder="Subcategory" /></SelectTrigger>
                <SelectContent className="bg-popover max-h-72">
                  <SelectItem value={ANY}>None</SelectItem>
                  {subs.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>
        )}
        {kind === "gst" && (
          <Select value={v} onValueChange={setV}>
            <SelectTrigger className="rounded-sm" data-testid="bulk-gst-select"><SelectValue placeholder="GST treatment" /></SelectTrigger>
            <SelectContent className="bg-popover">
              {Object.entries(GST_LABELS).map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        {kind === "tag" && (
          <Input value={v} onChange={(e) => setV(e.target.value)} placeholder="Tag name" className="rounded-sm" data-testid="bulk-tag-input" />
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button data-testid="bulk-apply" className="rounded-sm bg-primary text-primary-foreground" disabled={!v}
            onClick={() => onApply(
              kind === "category" ? "change_category" : kind === "gst" ? "change_gst" : "add_tag",
              kind === "category" ? { category_id: v, subcategory_id: sub === ANY ? null : sub }
                : kind === "gst" ? { gst_treatment: v } : { tag: v })}>
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TxnDetail({ txn, onClose }) {
  const { bump } = useApp();
  const [t, setT] = useState(txn);
  const [edit, setEdit] = useState(false);
  const [note, setNote] = useState(txn.accountant_note || "");
  const [uploading, setUploading] = useState(false);

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("linked_type", "transaction");
      fd.append("linked_id", t.txn_id);
      fd.append("doc_date", t.date);
      if (t.category_id) fd.append("category_id", t.category_id);
      if (t.supplier_id) fd.append("supplier_id", t.supplier_id);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const { data } = await api.get(`/transactions/${t.txn_id}`);
      setT(data);
      toast.success("Receipt attached");
      bump();
    } catch (e) { toast.error(errText(e)); } finally { setUploading(false); }
  };

  const flag = async () => {
    try {
      await api.post(`/transactions/${t.txn_id}/ask-accountant`, { ask_accountant: !t.ask_accountant, accountant_note: note });
      setT({ ...t, ask_accountant: !t.ask_accountant, accountant_note: note });
      toast.success("Flag updated");
      bump();
    } catch (e) { toast.error(errText(e)); }
  };

  const remove = async () => {
    try {
      await api.delete(`/transactions/${t.txn_id}`);
      toast.success("Archived (soft-deleted) — financial records are never destroyed");
      bump();
      onClose();
    } catch (e) { toast.error(errText(e)); }
  };

  if (edit) {
    return <QuickAdd type={t.txn_type} onClose={onClose} onSaved={onClose} defaults={{
      date: t.date, amount: String(t.amount_inc), description: t.description,
      category_id: t.category_id || "__none__", subcategory_id: t.subcategory_id || "__none__",
      supplier_id: t.supplier_id || "__none__", account_id: t.account_id || "__none__",
      gst_treatment: t.gst_treatment, reference: t.reference, notes: t.notes,
      tags: (t.tags || []).join(", "),
    }} />;
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="bg-popover max-w-xl rounded-sm max-h-[90vh] overflow-y-auto" data-testid="txn-detail-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">{t.description || TXN_TYPE_LABELS[t.txn_type]}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs">
          {[["Date", fmtDate(t.date)], ["Financial year", t.fy.replace("FY", "FY ")], ["Month", t.month_label],
            ["Type", TXN_TYPE_LABELS[t.txn_type]], ["Category", t.category_name || "Uncategorised"],
            ["Subcategory", t.subcategory_name || "—"], ["Supplier", t.supplier_name || "—"],
            ["Payment method", t.account_name || "—"], ["Amount ex GST", fmtMoney(t.amount_ex)],
            ["GST", fmtMoney(t.gst)], ["Amount inc GST", fmtMoney(t.amount_inc)],
            ["GST treatment", GST_LABELS[t.gst_treatment]], ["Reference", t.reference || "—"],
            ["Reconciliation", t.reconcile_status], ["Created", `${fmtDate(t.created_at)} · ${t.created_by || "—"}`],
            ["Last edited", `${fmtDate(t.updated_at)} · ${t.updated_by || "—"}`]].map(([l, v]) => (
            <div key={l}>
              <div className="overline">{l}</div>
              <div className="num mt-0.5">{v}</div>
            </div>
          ))}
        </div>
        {t.notes && <p className="text-xs border-l-2 border-border pl-3 mt-3">{t.notes}</p>}

        <div className="border-t border-border pt-3 mt-3 space-y-3">
          <div>
            <div className="overline mb-1.5">Receipts ({t.receipt_document_ids?.length || 0})</div>
            <div className="flex flex-wrap gap-2 items-center">
              {(t.receipt_document_ids || []).map((id) => (
                <Button key={id} size="sm" variant="outline" className="rounded-sm text-xs h-7"
                  data-testid={`view-receipt-${id}`}
                  onClick={() => downloadFile(`/documents/${id}/download`, `receipt-${id}`)}>
                  <Download size={11} className="mr-1" /> Receipt
                </Button>
              ))}
              <Label className="text-xs cursor-pointer inline-flex items-center gap-1.5 border border-border px-2 py-1 rounded-sm hover:bg-accent">
                <Upload size={12} /> {uploading ? "Uploading…" : "Attach receipt"}
                <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp"
                  data-testid="txn-upload-receipt" onChange={(e) => upload(e.target.files?.[0])} />
              </Label>
            </div>
          </div>

          <div>
            <div className="overline mb-1.5">Ask accountant</div>
            <Input value={note} onChange={(e) => setNote(e.target.value)} className="rounded-sm text-xs"
              placeholder="e.g. Please check GST treatment" data-testid="txn-accountant-note" />
            <Button size="sm" variant={t.ask_accountant ? "default" : "outline"} onClick={flag}
              className="rounded-sm mt-2 text-xs gap-1.5" data-testid="txn-flag-accountant">
              <MessageCircleQuestion size={13} /> {t.ask_accountant ? "Remove flag" : "Flag for accountant"}
            </Button>
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" className="rounded-sm text-negative gap-1.5" onClick={remove} data-testid="txn-delete">
            <Trash2 size={13} /> Archive
          </Button>
          <Button variant="outline" className="rounded-sm gap-1.5" onClick={() => setEdit(true)} data-testid="txn-edit">
            <Pencil size={13} /> Edit
          </Button>
          <Button className="rounded-sm bg-primary text-primary-foreground" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
