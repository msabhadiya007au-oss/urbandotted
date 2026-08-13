import React, { useState, useEffect } from "react";
import { toast } from "sonner";
import { api, errText, todayISO, GST_LABELS } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const TITLES = {
  expense: "Add Expense", sale: "Add Sale", refund: "Add Refund",
  inventory: "Add Inventory Purchase", asset: "Add Asset", receipt: "Upload Receipt",
};

export function useLookups() {
  const [data, setData] = useState({ categories: [], flat: [], suppliers: [], accounts: [], products: [] });
  useEffect(() => {
    Promise.all([
      api.get("/categories"), api.get("/suppliers"), api.get("/accounts"), api.get("/products"),
    ]).then(([c, s, a, p]) => setData({
      categories: c.data.tree, flat: c.data.flat, suppliers: s.data, accounts: a.data, products: p.data,
    })).catch(() => {});
  }, []);
  return data;
}

const NONE = "__none__";
const val = (v) => (v === NONE ? null : v || null);

export default function QuickAdd({ type, onClose, defaults = {}, onSaved }) {
  const { bump, fy } = useApp();
  const lk = useLookups();
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({
    date: todayISO(), amount: "", description: "", category_id: NONE, subcategory_id: NONE,
    supplier_id: NONE, account_id: NONE, gst_treatment: "gst_included", gst_rate: "",
    reference: "", notes: "", tags: "", ask_accountant: false, accountant_note: "",
    recurring: false, sku: "", qty: "", unit_cost: "", freight: "", customs: "",
    import_gst: "", other_landed: "", name: "", invoice: "", serial: "", asset_category: "",
    business_use_pct: 100, status: "in_use", needs_review: false, gross: "", discounts: "",
    shipping_revenue: "", fees: "", gift_cards: "", other_income: "", reason: "",
    original_order: "", items_qty: "", file: null, ...defaults,
  });
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }));
  const kindFilter = type === "sale" || type === "refund" ? "income" : "expense";
  const parents = (lk.categories || []).filter((c) => c.kind === kindFilter);
  const subs = parents.find((c) => c.category_id === f.category_id)?.children || [];

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (type === "receipt") {
        if (!f.file) throw new Error("Choose a file first");
        const fd = new FormData();
        fd.append("file", f.file);
        fd.append("doc_date", f.date);
        if (val(f.category_id)) fd.append("category_id", val(f.category_id));
        if (val(f.supplier_id)) fd.append("supplier_id", val(f.supplier_id));
        fd.append("notes", f.notes || "");
        await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        toast.success("Receipt uploaded to the document vault");
      } else if (type === "inventory") {
        await api.post("/inventory/purchases", {
          date: f.date, supplier_id: val(f.supplier_id), product_id: val(f.product_id),
          sku: f.sku, description: f.description, qty: parseInt(f.qty || 0, 10),
          unit_cost: parseFloat(f.unit_cost || 0), freight: parseFloat(f.freight || 0),
          customs: parseFloat(f.customs || 0), import_gst: parseFloat(f.import_gst || 0),
          other_landed: parseFloat(f.other_landed || 0), reference: f.reference, notes: f.notes,
        });
        toast.success("Inventory purchase recorded");
      } else if (type === "asset") {
        await api.post("/assets", {
          name: f.name, date: f.date, supplier_id: val(f.supplier_id), invoice: f.invoice,
          price: parseFloat(f.amount || 0), gst_treatment: f.gst_treatment, serial: f.serial,
          asset_category: f.asset_category, business_use_pct: parseInt(f.business_use_pct, 10),
          status: f.status, notes: f.notes, needs_review: f.needs_review,
        });
        toast.success("Asset added to the register");
      } else {
        const payload = {
          txn_type: type, date: f.date, amount: parseFloat(f.amount || 0),
          category_id: val(f.category_id), subcategory_id: val(f.subcategory_id),
          supplier_id: val(f.supplier_id), account_id: val(f.account_id),
          description: f.description, gst_treatment: f.gst_treatment,
          gst_rate: f.gst_treatment === "custom" && f.gst_rate ? String(parseFloat(f.gst_rate) / 100) : null,
          reference: f.reference, notes: f.notes,
          tags: f.tags ? f.tags.split(",").map((t) => t.trim()).filter(Boolean) : [],
          ask_accountant: f.ask_accountant, accountant_note: f.accountant_note,
        };
        if (type === "sale") {
          payload.sale = {
            gross: parseFloat(f.amount || 0), discounts: parseFloat(f.discounts || 0),
            shipping_revenue: parseFloat(f.shipping_revenue || 0),
            other_income: parseFloat(f.other_income || 0), gift_cards: parseFloat(f.gift_cards || 0),
            fees: parseFloat(f.fees || 0),
          };
          if (f.sku && f.items_qty) payload.items = [{ sku: f.sku, qty: parseInt(f.items_qty, 10) }];
        }
        if (type === "refund") {
          payload.refund = { reason: f.reason, original_order: f.original_order, sku: f.sku };
        }
        await api.post("/transactions", payload);
        toast.success(`${TITLES[type].replace("Add ", "")} saved`);
      }
      bump();
      onSaved?.();
      onClose();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setSaving(false);
    }
  };

  const Field = ({ label, children, hint }) => (
    <div className="space-y-1.5">
      <Label className="overline">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  );

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-popover max-w-2xl max-h-[92vh] overflow-y-auto rounded-sm" data-testid={`quick-add-dialog-${type}`}>
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl">{TITLES[type]}</DialogTitle>
          <DialogDescription className="text-xs">
            Financial year is derived from the date (1 July – 30 June). All amounts in AUD.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Date">
              <Input type="date" value={f.date} onChange={(e) => set("date")(e.target.value)}
                required className="num rounded-sm" data-testid="qa-date" />
            </Field>

            {type === "asset" && (
              <Field label="Asset name">
                <Input value={f.name} onChange={(e) => set("name")(e.target.value)} required
                  className="rounded-sm" data-testid="qa-asset-name" placeholder="Heat press machine" />
              </Field>
            )}

            {type !== "receipt" && type !== "inventory" && (
              <Field label={type === "asset" ? "Purchase price" : type === "sale" ? "Gross sales amount" : "Amount"}>
                <Input type="number" step="0.01" min="0.01" value={f.amount} required
                  onChange={(e) => set("amount")(e.target.value)} className="num rounded-sm"
                  data-testid="qa-amount" placeholder="0.00" />
              </Field>
            )}

            {type === "receipt" && (
              <Field label="File" hint="PDF, JPG, PNG or WEBP · max 10MB">
                <Input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" data-testid="qa-file"
                  onChange={(e) => set("file")(e.target.files?.[0] || null)} className="rounded-sm text-xs" />
              </Field>
            )}

            {(type === "expense" || type === "sale" || type === "refund" || type === "receipt") && (
              <>
                <Field label="Category">
                  <Select value={f.category_id} onValueChange={(v) => { set("category_id")(v); set("subcategory_id")(NONE); }}>
                    <SelectTrigger className="rounded-sm" data-testid="qa-category"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent className="bg-popover max-h-72">
                      <SelectItem value={NONE}>Uncategorised</SelectItem>
                      {parents.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Field>
                {subs.length > 0 && (
                  <Field label="Subcategory">
                    <Select value={f.subcategory_id} onValueChange={set("subcategory_id")}>
                      <SelectTrigger className="rounded-sm" data-testid="qa-subcategory"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent className="bg-popover max-h-72">
                        <SelectItem value={NONE}>None</SelectItem>
                        {subs.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </Field>
                )}
              </>
            )}

            {type !== "receipt" && (
              <Field label="Supplier">
                <Select value={f.supplier_id} onValueChange={set("supplier_id")}>
                  <SelectTrigger className="rounded-sm" data-testid="qa-supplier"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent className="bg-popover max-h-72">
                    <SelectItem value={NONE}>None</SelectItem>
                    {lk.suppliers.map((s) => <SelectItem key={s.supplier_id} value={s.supplier_id}>{s.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            )}

            {(type === "expense" || type === "sale" || type === "refund") && (
              <Field label="Payment method / account">
                <Select value={f.account_id} onValueChange={set("account_id")}>
                  <SelectTrigger className="rounded-sm" data-testid="qa-account"><SelectValue placeholder="Select" /></SelectTrigger>
                  <SelectContent className="bg-popover max-h-72">
                    <SelectItem value={NONE}>None</SelectItem>
                    {lk.accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            )}

            {type !== "receipt" && type !== "inventory" && (
              <Field label="GST treatment" hint="GST is per transaction — never assumed to be 10%.">
                <Select value={f.gst_treatment} onValueChange={set("gst_treatment")}>
                  <SelectTrigger className="rounded-sm" data-testid="qa-gst"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-popover">
                    {Object.entries(GST_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                  </SelectContent>
                </Select>
              </Field>
            )}

            {f.gst_treatment === "custom" && type !== "receipt" && type !== "inventory" && (
              <Field label="Custom rate (%)" hint="Enter as a percentage, e.g. 5 for 5%.">
                <Input type="number" step="0.01" min="0" max="100" value={f.gst_rate}
                  onChange={(e) => set("gst_rate")(e.target.value)}
                  className="num rounded-sm" data-testid="qa-gst-rate" placeholder="5" />
              </Field>
            )}

            {type === "inventory" && (
              <>
                <Field label="SKU">
                  <Input value={f.sku} onChange={(e) => set("sku")(e.target.value)} className="num rounded-sm"
                    data-testid="qa-sku" placeholder="CASE-IP15" />
                </Field>
                <Field label="Quantity">
                  <Input type="number" min="1" value={f.qty} required onChange={(e) => set("qty")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-qty" placeholder="1000" />
                </Field>
                <Field label="Unit cost">
                  <Input type="number" step="0.01" value={f.unit_cost} required onChange={(e) => set("unit_cost")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-unit-cost" placeholder="5.00" />
                </Field>
                <Field label="Freight">
                  <Input type="number" step="0.01" value={f.freight} onChange={(e) => set("freight")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-freight" placeholder="500" />
                </Field>
                <Field label="Customs / duty">
                  <Input type="number" step="0.01" value={f.customs} onChange={(e) => set("customs")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-customs" placeholder="300" />
                </Field>
                <Field label="Import GST">
                  <Input type="number" step="0.01" value={f.import_gst} onChange={(e) => set("import_gst")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-import-gst" placeholder="580" />
                </Field>
                <Field label="Other landed costs">
                  <Input type="number" step="0.01" value={f.other_landed} onChange={(e) => set("other_landed")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-other-landed" placeholder="100" />
                </Field>
              </>
            )}

            {type === "sale" && (
              <>
                <Field label="Discounts">
                  <Input type="number" step="0.01" value={f.discounts} onChange={(e) => set("discounts")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-discounts" placeholder="0.00" />
                </Field>
                <Field label="Shipping revenue">
                  <Input type="number" step="0.01" value={f.shipping_revenue} onChange={(e) => set("shipping_revenue")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-shipping-revenue" placeholder="0.00" />
                </Field>
                <Field label="Payment gateway fees">
                  <Input type="number" step="0.01" value={f.fees} onChange={(e) => set("fees")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-fees" placeholder="0.00" />
                </Field>
                <Field label="Gift cards">
                  <Input type="number" step="0.01" value={f.gift_cards} onChange={(e) => set("gift_cards")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-gift-cards" placeholder="0.00" />
                </Field>
                <Field label="SKU sold (for COGS)">
                  <Input value={f.sku} onChange={(e) => set("sku")(e.target.value)} className="num rounded-sm"
                    data-testid="qa-sale-sku" placeholder="CASE-IP15" />
                </Field>
                <Field label="Units sold (for COGS)">
                  <Input type="number" value={f.items_qty} onChange={(e) => set("items_qty")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-sale-qty" placeholder="120" />
                </Field>
              </>
            )}

            {type === "refund" && (
              <>
                <Field label="Refund reason">
                  <Input value={f.reason} onChange={(e) => set("reason")(e.target.value)} className="rounded-sm"
                    data-testid="qa-reason" placeholder="Change of mind" />
                </Field>
                <Field label="Original order">
                  <Input value={f.original_order} onChange={(e) => set("original_order")(e.target.value)}
                    className="num rounded-sm" data-testid="qa-original-order" placeholder="#1042" />
                </Field>
                <Field label="Product SKU">
                  <Input value={f.sku} onChange={(e) => set("sku")(e.target.value)} className="num rounded-sm"
                    data-testid="qa-refund-sku" placeholder="CASE-IP15" />
                </Field>
              </>
            )}

            {type === "asset" && (
              <>
                <Field label="Invoice number">
                  <Input value={f.invoice} onChange={(e) => set("invoice")(e.target.value)} className="num rounded-sm" data-testid="qa-invoice" />
                </Field>
                <Field label="Serial number">
                  <Input value={f.serial} onChange={(e) => set("serial")(e.target.value)} className="num rounded-sm" data-testid="qa-serial" />
                </Field>
                <Field label="Asset category">
                  <Input value={f.asset_category} onChange={(e) => set("asset_category")(e.target.value)}
                    className="rounded-sm" data-testid="qa-asset-category" placeholder="Machinery & Equipment" />
                </Field>
                <Field label="Business-use %">
                  <Input type="number" min="0" max="100" value={f.business_use_pct}
                    onChange={(e) => set("business_use_pct")(e.target.value)} className="num rounded-sm" data-testid="qa-business-use" />
                </Field>
              </>
            )}

            {type !== "receipt" && (
              <Field label="Reference / invoice number">
                <Input value={f.reference} onChange={(e) => set("reference")(e.target.value)}
                  className="num rounded-sm" data-testid="qa-reference" />
              </Field>
            )}
          </div>

          {type !== "asset" && type !== "receipt" && (
            <Field label="Description">
              <Input value={f.description} onChange={(e) => set("description")(e.target.value)}
                className="rounded-sm" data-testid="qa-description" placeholder="What was this for?" />
            </Field>
          )}

          <Field label="Notes">
            <Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} rows={2}
              className="rounded-sm text-sm" data-testid="qa-notes" />
          </Field>

          {(type === "expense" || type === "sale" || type === "refund") && (
            <>
              <Field label="Tags (comma separated)">
                <Input value={f.tags} onChange={(e) => set("tags")(e.target.value)} className="rounded-sm"
                  data-testid="qa-tags" placeholder="q1, review" />
              </Field>
              <div className="flex items-start gap-3 p-3 border border-border rounded-sm bg-muted/30">
                <Switch checked={f.ask_accountant} onCheckedChange={set("ask_accountant")} data-testid="qa-ask-accountant" />
                <div className="flex-1">
                  <p className="text-xs font-semibold">Flag: ASK ACCOUNTANT</p>
                  <p className="text-[10px] text-muted-foreground">Adds this to the Accountant Questions report.</p>
                  {f.ask_accountant && (
                    <Textarea rows={2} value={f.accountant_note} onChange={(e) => set("accountant_note")(e.target.value)}
                      className="mt-2 rounded-sm text-xs" data-testid="qa-accountant-note"
                      placeholder="e.g. Not sure whether this is deductible — please check GST." />
                  )}
                </div>
              </div>
            </>
          )}

          {type === "asset" && (
            <div className="flex items-center gap-3 p-3 border border-border rounded-sm bg-muted/30">
              <Switch checked={f.needs_review} onCheckedChange={set("needs_review")} data-testid="qa-needs-review" />
              <p className="text-xs">Needs accountant review (asset vs expense, business use, depreciation)</p>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={onClose} className="rounded-sm" data-testid="qa-cancel">Cancel</Button>
            <Button type="submit" disabled={saving} className="rounded-sm bg-primary text-primary-foreground" data-testid="qa-submit">
              {saving ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
