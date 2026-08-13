import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, fmtMoney, fmtNum, fmtDate, errText } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  PageHeader, Section, Loading, Empty, Money, KpiCard, MonthBarChart, MonthLineChart,
  toChart, Pill, Disclaimer,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import QuickAdd from "@/components/QuickAdd";
import { Plus, ArrowLeft, Upload, Trash2 } from "lucide-react";

export function Inventory() {
  const { fy, refreshKey, bump } = useApp();
  const [d, setD] = useState(null);
  const [add, setAdd] = useState(false);

  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/inventory/purchases?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);

  const upload = async (purchaseId, file, date) => {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("linked_type", "inventory_purchase");
      fd.append("linked_id", purchaseId);
      fd.append("doc_date", date);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Receipt attached"); bump();
    } catch (e) { toast.error(errText(e)); }
  };

  const remove = async (id) => {
    try { await api.delete(`/inventory/purchases/${id}`); toast.success("Purchase archived"); bump(); }
    catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <Loading label="Loading inventory" />;
  const t = d.totals;

  return (
    <div data-testid="inventory-page">
      <PageHeader title="Inventory Purchases"
        subtitle="Landed cost tracking: goods + freight + customs + import GST + other costs, giving a true landed unit cost.">
        <Button size="sm" className="rounded-sm gap-1.5 bg-primary text-primary-foreground"
          onClick={() => setAdd(true)} data-testid="add-purchase-btn"><Plus size={14} /> New purchase</Button>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-4">
        <KpiCard label="Purchase Total" value={t.purchase_total} testId="inv-total" />
        <KpiCard label="Import GST" value={t.import_gst} to="/gst" testId="inv-import-gst" />
        <KpiCard label="Units Purchased" value={fmtNum(t.units_purchased)} testId="inv-units" />
        <KpiCard label="Units Sold" value={fmtNum(t.units_sold)} to="/cogs" testId="inv-units-sold" />
        <KpiCard label="Units Remaining" value={fmtNum(t.units_remaining)} testId="inv-units-remaining" />
      </div>

      <Disclaimer>Purchasing inventory is not the same as cost of goods sold. COGS is recognised when
        units sell — see the COGS page for the derivation.</Disclaimer>

      <Section title={`Purchases (${d.items.length})`} className="mt-4" testId="inventory-table">
        {d.items.length === 0 ? <Empty title="No inventory purchases yet" hint="+ Add → Add Inventory Purchase" /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "Supplier", "SKU", "Qty", "Unit Cost", "Freight", "Customs", "Import GST",
                  "Other", "Total Cost", "Landed Unit", "Sold", "Left", "Receipt", ""].map((h, i) => (
                  <TableHead key={h + i} className={`overline ${i > 2 ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {d.items.map((p) => (
                  <TableRow key={p.purchase_id} data-testid={`purchase-row-${p.purchase_id}`}>
                    <TableCell className="num text-xs whitespace-nowrap">{fmtDate(p.date)}</TableCell>
                    <TableCell className="text-xs">{p.supplier_name || "—"}</TableCell>
                    <TableCell className="num text-xs">{p.sku || "—"}</TableCell>
                    <TableCell className="text-right num text-xs">{fmtNum(p.qty)}</TableCell>
                    {["unit_cost", "freight", "customs", "import_gst", "other_landed", "total_cost", "landed_unit_cost"].map((k) => (
                      <TableCell key={k} className="text-right"><Money value={p[k]} className="text-xs" /></TableCell>))}
                    <TableCell className="text-right num text-xs">{fmtNum(p.qty_sold)}</TableCell>
                    <TableCell className="text-right num text-xs">{fmtNum(p.qty_remaining)}</TableCell>
                    <TableCell className="text-right">
                      {p.has_receipt ? <Pill tone="positive">Attached</Pill> : (
                        <Label className="cursor-pointer inline-flex" data-testid={`upload-purchase-${p.purchase_id}`}>
                          <Upload size={12} className="text-muted-foreground hover:text-foreground" />
                          <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp"
                            onChange={(e) => upload(p.purchase_id, e.target.files?.[0], p.date)} />
                        </Label>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <button onClick={() => remove(p.purchase_id)} data-testid={`delete-purchase-${p.purchase_id}`}
                        className="text-muted-foreground hover:text-negative"><Trash2 size={12} /></button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {add && <QuickAdd type="inventory" onClose={() => setAdd(false)} />}
    </div>
  );
}

export function Cogs() {
  const { fy, refreshKey, bump } = useApp();
  const [d, setD] = useState(null);
  const [manual, setManual] = useState(false);
  const [m, setM] = useState({ month_key: "", amount: "", sku: "", qty: "", description: "" });

  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/cogs?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);

  const save = async () => {
    try {
      await api.post("/cogs/manual", {
        month_key: m.month_key, amount: parseFloat(m.amount), sku: m.sku,
        qty: parseInt(m.qty || 0, 10), description: m.description,
      });
      toast.success("Manual COGS entry added"); setManual(false); bump();
    } catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <Loading label="Calculating COGS" />;

  return (
    <div data-testid="cogs-page">
      <PageHeader title="Cost of Goods Sold"
        subtitle="COGS is recognised when units sell, consuming inventory lots at their landed unit cost — not when stock is purchased.">
        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => setManual(true)} data-testid="add-manual-cogs">
          <Plus size={14} /> Manual COGS entry
        </Button>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-4">
        <KpiCard label={`FY COGS ${fy?.replace("FY", "")}`} value={d.total_cogs} testId="cogs-total" />
        <KpiCard label="Units Sold" value={fmtNum(d.total_units)} testId="cogs-units" />
        <KpiCard label="Inventory On Hand" value={d.inventory_on_hand_value} to="/inventory" testId="cogs-on-hand-value" />
        <KpiCard label="Units On Hand" value={fmtNum(d.units_on_hand)} testId="cogs-units-on-hand" />
        <KpiCard label="Unmatched Units Sold" value={fmtNum(d.unmatched_units_sold)}
          tone={d.unmatched_units_sold ? "warning" : "neutral"} testId="cogs-unmatched" />
      </div>

      <Disclaimer testId="cogs-methodology">{d.methodology}</Disclaimer>

      <div className="grid gap-4 lg:grid-cols-2 mt-4">
        <Section title="COGS by month" testId="cogs-chart">
          <div className="p-3"><MonthBarChart data={toChart(d.months, (mm) => ({ COGS: mm.cogs }))}
            keys={[{ key: "COGS", name: "COGS", color: "#B45309" }]} /></div>
        </Section>
        <Section title="Monthly COGS" testId="cogs-monthly-table">
          <div className="overflow-y-auto max-h-[320px]">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                <TableHead className="overline">Month</TableHead>
                <TableHead className="overline text-right">Units</TableHead>
                <TableHead className="overline text-right">COGS</TableHead>
                <TableHead className="overline text-right">Lines</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {d.months.map((mm) => (
                  <TableRow key={mm.month_key} data-testid={`cogs-month-${mm.month_key}`}>
                    <TableCell className="text-xs">{mm.month_label}</TableCell>
                    <TableCell className="text-right num text-xs">{fmtNum(mm.units)}</TableCell>
                    <TableCell className="text-right"><Money value={mm.cogs} className="text-xs" /></TableCell>
                    <TableCell className="text-right num text-xs">{mm.lines.length}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="bg-muted/40 font-semibold">
                  <TableCell className="text-xs">FY Total</TableCell>
                  <TableCell className="text-right num text-xs">{fmtNum(d.total_units)}</TableCell>
                  <TableCell className="text-right"><Money value={d.total_cogs} className="text-xs font-semibold" /></TableCell>
                  <TableCell />
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </Section>
      </div>

      <Section title="COGS calculation detail" className="mt-4" testId="cogs-lines">
        <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Month", "Source", "SKU", "Qty", "Landed Unit Cost", "COGS Amount", "Reference"].map((h, i) => (
                <TableHead key={h} className={`overline ${i > 2 ? "text-right" : ""}`}>{h}</TableHead>))}
            </TableRow></TableHeader>
            <TableBody>
              {d.months.flatMap((mm) => mm.lines.map((l, i) => (
                <TableRow key={`${mm.month_key}-${i}`} data-testid={`cogs-line-${mm.month_key}-${i}`}>
                  <TableCell className="text-xs">{mm.month_label}</TableCell>
                  <TableCell className="text-xs"><Pill tone={l.source === "manual" ? "warning" : "neutral"}>{l.source}</Pill></TableCell>
                  <TableCell className="num text-xs">{l.sku || "—"}</TableCell>
                  <TableCell className="text-right num text-xs">{fmtNum(l.qty)}</TableCell>
                  <TableCell className="text-right"><Money value={l.unit_cost} className="text-xs" /></TableCell>
                  <TableCell className="text-right"><Money value={l.amount} className="text-xs font-semibold" /></TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-[220px] truncate">{l.description || "—"}</TableCell>
                </TableRow>
              )))}
            </TableBody>
          </Table>
          {d.total_units === 0 && <Empty title="No COGS yet"
            hint="Record inventory purchases with a SKU, then record sales with the same SKU and units sold." />}
        </div>
      </Section>

      {manual && (
        <Dialog open onOpenChange={() => setManual(false)}>
          <DialogContent className="bg-popover rounded-sm" data-testid="manual-cogs-dialog">
            <DialogHeader><DialogTitle className="font-serif text-xl">Manual COGS entry</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <div><Label className="overline">Month (YYYY-MM)</Label>
                <Input value={m.month_key} onChange={(e) => setM({ ...m, month_key: e.target.value })}
                  placeholder="2025-09" className="rounded-sm num" data-testid="manual-cogs-month" /></div>
              <div><Label className="overline">COGS amount</Label>
                <Input type="number" step="0.01" value={m.amount} onChange={(e) => setM({ ...m, amount: e.target.value })}
                  className="rounded-sm num" data-testid="manual-cogs-amount" /></div>
              <div><Label className="overline">SKU (optional)</Label>
                <Input value={m.sku} onChange={(e) => setM({ ...m, sku: e.target.value })} className="rounded-sm num" data-testid="manual-cogs-sku" /></div>
              <div><Label className="overline">Units (optional)</Label>
                <Input type="number" value={m.qty} onChange={(e) => setM({ ...m, qty: e.target.value })} className="rounded-sm num" data-testid="manual-cogs-qty" /></div>
              <div><Label className="overline">Description</Label>
                <Input value={m.description} onChange={(e) => setM({ ...m, description: e.target.value })} className="rounded-sm" data-testid="manual-cogs-description" /></div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setManual(false)} className="rounded-sm">Cancel</Button>
              <Button onClick={save} disabled={!m.month_key || !m.amount} data-testid="manual-cogs-save"
                className="rounded-sm bg-primary text-primary-foreground">Add entry</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

export function Assets() {
  const { fy, refreshKey, bump } = useApp();
  const [d, setD] = useState(null);
  const [add, setAdd] = useState(false);

  useEffect(() => {
    if (!fy) return; setD(null);
    api.get(`/assets?fy=${fy}`).then(({ data }) => setD(data)).catch(() => setD(false));
  }, [fy, refreshKey]);

  const upload = async (assetId, file, date) => {
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("linked_type", "asset");
      fd.append("linked_id", assetId); fd.append("doc_date", date);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Receipt attached"); bump();
    } catch (e) { toast.error(errText(e)); }
  };

  if (!d) return <Loading label="Loading asset register" />;
  const t = d.totals;

  return (
    <div data-testid="assets-page">
      <PageHeader title="Assets &amp; Machinery" subtitle="A separate register for equipment and expensive purchases.">
        <Button size="sm" className="rounded-sm gap-1.5 bg-primary text-primary-foreground"
          onClick={() => setAdd(true)} data-testid="add-asset-btn"><Plus size={14} /> New asset</Button>
      </PageHeader>

      <div className="grid grid-cols-2 md:grid-cols-5 border border-border bg-border mb-4">
        <KpiCard label="Assets" value={String(t.count)} testId="asset-count" />
        <KpiCard label="Total Ex GST" value={t.price_ex} testId="asset-ex" />
        <KpiCard label="GST Recorded" value={t.gst} to="/gst" testId="asset-gst" />
        <KpiCard label="Total Inc GST" value={t.price_inc} testId="asset-inc" />
        <KpiCard label="Needs Review" value={String(t.needs_review)} tone={t.needs_review ? "warning" : "neutral"} testId="asset-review" />
      </div>

      <Disclaimer testId="asset-disclaimer">{d.disclaimer}</Disclaimer>

      <Section title={`Asset register (${d.items.length})`} className="mt-4" testId="assets-table">
        {d.items.length === 0 ? <Empty title="No assets recorded" hint="+ Add → Add Asset" /> : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Date", "Asset", "Supplier", "Invoice", "Serial", "Ex GST", "GST", "Inc GST",
                  "Business Use", "Status", "Receipt", "Review"].map((h, i) => (
                  <TableHead key={h} className={`overline ${i > 4 ? "text-right" : ""}`}>{h}</TableHead>))}
              </TableRow></TableHeader>
              <TableBody>
                {d.items.map((a) => (
                  <TableRow key={a.asset_id} data-testid={`asset-row-${a.asset_id}`}>
                    <TableCell className="num text-xs whitespace-nowrap">{fmtDate(a.date)}</TableCell>
                    <TableCell className="text-xs font-semibold">{a.name}</TableCell>
                    <TableCell className="text-xs">{a.supplier_name || "—"}</TableCell>
                    <TableCell className="num text-xs">{a.invoice || "—"}</TableCell>
                    <TableCell className="num text-xs">{a.serial || "—"}</TableCell>
                    <TableCell className="text-right"><Money value={a.price_ex} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={a.gst} className="text-xs" /></TableCell>
                    <TableCell className="text-right"><Money value={a.price_inc} className="text-xs font-semibold" /></TableCell>
                    <TableCell className="text-right num text-xs">{a.business_use_pct}%</TableCell>
                    <TableCell className="text-right text-xs capitalize">{a.status?.replace("_", " ")}</TableCell>
                    <TableCell className="text-right">
                      {a.has_receipt ? <Pill tone="positive">Attached</Pill> : (
                        <Label className="cursor-pointer inline-flex" data-testid={`upload-asset-${a.asset_id}`}>
                          <Upload size={12} className="text-muted-foreground hover:text-foreground" />
                          <input type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp"
                            onChange={(e) => upload(a.asset_id, e.target.files?.[0], a.date)} />
                        </Label>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {a.needs_review ? <Pill tone="warning">Accountant</Pill> : <Pill tone="positive">OK</Pill>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {add && <QuickAdd type="asset" onClose={() => setAdd(false)} />}
    </div>
  );
}
