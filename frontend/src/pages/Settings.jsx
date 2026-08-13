import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, fmtMoney, fmtDate, errText, downloadFile, GST_LABELS } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Money, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useLookups } from "@/components/QuickAdd";
import { Plus, Trash2, Database, Download, RefreshCw } from "lucide-react";

const NONE = "__none__";

export default function Settings() {
  const { refreshKey, bump, user } = useApp();
  const [tab, setTab] = useState("business");

  return (
    <div data-testid="settings-page">
      <PageHeader title="Settings" subtitle={`Signed in as ${user?.email} · ${user?.auth_provider === "google" ? "Google account" : "Email & password"}`} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm bg-muted h-9 flex-wrap h-auto">
          {[["business", "Business"], ["accounts", "Payment Accounts"], ["products", "Products"],
            ["recurring", "Recurring Expenses"], ["demo", "Demo Data"], ["integrations", "Integrations"],
            ["backup", "Backup"], ["audit", "Audit Log"]].map(([k, l]) => (
            <TabsTrigger key={k} value={k} className="rounded-sm text-xs" data-testid={`settings-tab-${k}`}>{l}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="business" className="mt-4"><BusinessSettings /></TabsContent>
        <TabsContent value="accounts" className="mt-4"><Accounts /></TabsContent>
        <TabsContent value="products" className="mt-4"><Products /></TabsContent>
        <TabsContent value="recurring" className="mt-4"><Recurring /></TabsContent>
        <TabsContent value="demo" className="mt-4"><DemoData /></TabsContent>
        <TabsContent value="integrations" className="mt-4"><Integrations /></TabsContent>
        <TabsContent value="backup" className="mt-4"><Backup /></TabsContent>
        <TabsContent value="audit" className="mt-4"><AuditLog /></TabsContent>
      </Tabs>
    </div>
  );
}

function BusinessSettings() {
  const { bump } = useApp();
  const [b, setB] = useState(null);
  useEffect(() => { api.get("/business").then(({ data }) => setB(data)).catch(() => setB(false)); }, []);
  const save = async () => {
    try {
      await api.put("/business", {
        name: b.name, abn: b.abn || "", gst_registered: !!b.gst_registered,
        default_gst_rate: b.default_gst_rate || "0.10", currency: b.currency || "AUD",
        timezone: b.timezone || "Australia/Adelaide",
      });
      toast.success("Business settings saved"); bump();
    } catch (e) { toast.error(errText(e)); }
  };
  if (!b) return <Loading />;
  return (
    <Section title="Business details" testId="business-settings">
      <div className="p-4 grid gap-4 sm:grid-cols-2 max-w-2xl">
        <div><Label className="overline">Business name</Label>
          <Input value={b.name} onChange={(e) => setB({ ...b, name: e.target.value })} className="rounded-sm" data-testid="business-name" /></div>
        <div><Label className="overline">ABN</Label>
          <Input value={b.abn || ""} onChange={(e) => setB({ ...b, abn: e.target.value })} className="rounded-sm num" data-testid="business-abn" /></div>
        <div><Label className="overline">Default GST rate (decimal)</Label>
          <Input value={b.default_gst_rate} onChange={(e) => setB({ ...b, default_gst_rate: e.target.value })}
            className="rounded-sm num" data-testid="business-gst-rate" /></div>
        <div><Label className="overline">Currency</Label>
          <Input value={b.currency} onChange={(e) => setB({ ...b, currency: e.target.value })} className="rounded-sm num" data-testid="business-currency" /></div>
        <div><Label className="overline">Timezone</Label>
          <Input value={b.timezone} onChange={(e) => setB({ ...b, timezone: e.target.value })} className="rounded-sm num" data-testid="business-timezone" /></div>
        <div className="flex items-center gap-3 pt-6">
          <Switch checked={!!b.gst_registered} onCheckedChange={(v) => setB({ ...b, gst_registered: v })} data-testid="business-gst-registered" />
          <span className="text-xs">Registered for GST</span>
        </div>
        <div className="sm:col-span-2">
          <Button onClick={save} className="rounded-sm bg-primary text-primary-foreground" data-testid="business-save">Save settings</Button>
        </div>
        <div className="sm:col-span-2">
          <Disclaimer>The default GST rate only pre-fills new transactions. Every transaction keeps its own GST treatment.</Disclaimer>
        </div>
      </div>
    </Section>
  );
}

function Accounts() {
  const { bump, refreshKey } = useApp();
  const [list, setList] = useState(null);
  const [name, setName] = useState("");
  const load = () => api.get("/accounts").then(({ data }) => setList(data)).catch(() => setList(false));
  useEffect(() => { load(); }, [refreshKey]); // eslint-disable-line
  const add = async () => {
    try { await api.post("/accounts", { name, type: "other" }); setName(""); load(); bump(); toast.success("Account added"); }
    catch (e) { toast.error(errText(e)); }
  };
  const archive = async (id) => {
    try { await api.post(`/accounts/${id}/archive`); load(); toast.success("Account archived"); }
    catch (e) { toast.error(errText(e)); }
  };
  if (!list) return <Loading />;
  return (
    <Section title={`Payment accounts (${list.length})`} testId="accounts-settings">
      <div className="divide-y divide-border">
        {list.map((a) => (
          <div key={a.account_id} className="flex items-center justify-between px-4 py-2.5" data-testid={`account-row-${a.account_id}`}>
            <span className="text-sm">{a.name}</span>
            <button onClick={() => archive(a.account_id)} className="text-muted-foreground hover:text-negative"
              data-testid={`account-archive-${a.account_id}`}><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
      <div className="p-4 border-t border-border flex gap-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New account name"
          className="rounded-sm max-w-xs text-sm" data-testid="account-name-input" />
        <Button size="sm" onClick={add} disabled={!name.trim()} className="rounded-sm gap-1.5" data-testid="account-add-btn">
          <Plus size={13} /> Add
        </Button>
      </div>
    </Section>
  );
}

function Products() {
  const { bump, refreshKey } = useApp();
  const [list, setList] = useState(null);
  const [f, setF] = useState({ sku: "", name: "" });
  const load = () => api.get("/products").then(({ data }) => setList(data)).catch(() => setList(false));
  useEffect(() => { load(); }, [refreshKey]); // eslint-disable-line
  const add = async () => {
    try { await api.post("/products", f); setF({ sku: "", name: "" }); load(); bump(); toast.success("Product added"); }
    catch (e) { toast.error(errText(e)); }
  };
  if (!list) return <Loading />;
  return (
    <Section title={`Products / SKUs (${list.length})`} testId="products-settings">
      <div className="divide-y divide-border">
        {list.map((p) => (
          <div key={p.product_id} className="flex items-center gap-4 px-4 py-2.5" data-testid={`product-row-${p.product_id}`}>
            <span className="num text-xs w-32">{p.sku}</span><span className="text-sm">{p.name}</span>
          </div>
        ))}
        {!list.length && <p className="text-xs text-muted-foreground p-6 text-center">No products yet — SKUs drive the COGS engine.</p>}
      </div>
      <div className="p-4 border-t border-border flex gap-2 flex-wrap">
        <Input value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} placeholder="SKU"
          className="rounded-sm max-w-[160px] text-sm num" data-testid="product-sku-input" />
        <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Product name"
          className="rounded-sm max-w-xs text-sm" data-testid="product-name-input" />
        <Button size="sm" onClick={add} disabled={!f.sku.trim() || !f.name.trim()} className="rounded-sm gap-1.5" data-testid="product-add-btn">
          <Plus size={13} /> Add
        </Button>
      </div>
    </Section>
  );
}

function Recurring() {
  const { bump, refreshKey, fy } = useApp();
  const lk = useLookups();
  const [list, setList] = useState(null);
  const [f, setF] = useState({ name: "", category_id: NONE, subcategory_id: NONE, frequency: "monthly",
    expected_amount: "", gst_treatment: "gst_included", start_month: "" });
  const load = () => api.get("/recurring").then(({ data }) => setList(data)).catch(() => setList(false));
  useEffect(() => { load(); }, [refreshKey]); // eslint-disable-line

  const parents = lk.flat.filter((c) => !c.parent_id && c.kind === "expense");
  const subs = lk.flat.filter((c) => c.parent_id === f.category_id);

  const add = async () => {
    try {
      await api.post("/recurring", {
        name: f.name, category_id: f.category_id === NONE ? null : f.category_id,
        subcategory_id: f.subcategory_id === NONE ? null : f.subcategory_id,
        frequency: f.frequency, expected_amount: f.expected_amount ? parseFloat(f.expected_amount) : null,
        variable: !f.expected_amount, gst_treatment: f.gst_treatment, is_active: true,
        start_month: f.start_month || null,
      });
      setF({ ...f, name: "", expected_amount: "" });
      load(); bump(); toast.success("Recurring template created");
    } catch (e) { toast.error(errText(e)); }
  };
  const remove = async (id) => {
    try { await api.delete(`/recurring/${id}`); load(); toast.success("Template removed"); }
    catch (e) { toast.error(errText(e)); }
  };
  const scan = async () => {
    try { const { data } = await api.post(`/reminders/scan?fy=${fy}`); toast.success(`${data.created} reminder(s) created`); bump(); }
    catch (e) { toast.error(errText(e)); }
  };
  if (!list) return <Loading />;

  return (
    <Section title={`Recurring expense templates (${list.length})`} testId="recurring-settings"
      right={<Button size="sm" variant="outline" className="rounded-sm text-xs gap-1.5" onClick={scan} data-testid="recurring-scan-btn">
        <RefreshCw size={12} /> Scan for missing entries</Button>}>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader><TableRow className="hover:bg-transparent">
            {["Name", "Category", "Frequency", "Expected", "GST", "Active", ""].map((h, i) => (
              <TableHead key={h + i} className={`overline ${i > 2 ? "text-right" : ""}`}>{h}</TableHead>))}
          </TableRow></TableHeader>
          <TableBody>
            {list.map((t) => (
              <TableRow key={t.template_id} data-testid={`recurring-row-${t.template_id}`}>
                <TableCell className="text-xs font-semibold">{t.name}</TableCell>
                <TableCell className="text-xs">{t.subcategory_name || t.category_name || "—"}</TableCell>
                <TableCell className="text-xs capitalize">{t.frequency}</TableCell>
                <TableCell className="text-right num text-xs">{t.expected_amount ? fmtMoney(t.expected_amount) : "Variable"}</TableCell>
                <TableCell className="text-right text-xs">{GST_LABELS[t.gst_treatment]}</TableCell>
                <TableCell className="text-right"><Pill tone={t.is_active ? "positive" : "neutral"}>{t.is_active ? "Active" : "Off"}</Pill></TableCell>
                <TableCell className="text-right">
                  <button onClick={() => remove(t.template_id)} className="text-muted-foreground hover:text-negative"
                    data-testid={`recurring-delete-${t.template_id}`}><Trash2 size={12} /></button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {!list.length && <Empty title="No recurring templates" hint="Add Shopify, electricity, internet, software and ad channels to enable missing-expense reminders." />}
      </div>

      <div className="p-4 border-t border-border grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div><Label className="overline">Name</Label>
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} className="rounded-sm" data-testid="recurring-name" /></div>
        <div><Label className="overline">Category</Label>
          <Select value={f.category_id} onValueChange={(v) => setF({ ...f, category_id: v, subcategory_id: NONE })}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="recurring-category"><SelectValue placeholder="Select" /></SelectTrigger>
            <SelectContent className="bg-popover max-h-72">
              <SelectItem value={NONE}>None</SelectItem>
              {parents.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select></div>
        {subs.length > 0 && (
          <div><Label className="overline">Subcategory</Label>
            <Select value={f.subcategory_id} onValueChange={(v) => setF({ ...f, subcategory_id: v })}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="recurring-subcategory"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent className="bg-popover max-h-72">
                <SelectItem value={NONE}>None</SelectItem>
                {subs.map((c) => <SelectItem key={c.category_id} value={c.category_id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select></div>
        )}
        <div><Label className="overline">Frequency</Label>
          <Select value={f.frequency} onValueChange={(v) => setF({ ...f, frequency: v })}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="recurring-frequency"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">
              {["monthly", "quarterly", "annually", "custom"].map((x) => <SelectItem key={x} value={x} className="capitalize">{x}</SelectItem>)}
            </SelectContent>
          </Select></div>
        <div><Label className="overline">Expected amount (blank = variable)</Label>
          <Input type="number" step="0.01" value={f.expected_amount} onChange={(e) => setF({ ...f, expected_amount: e.target.value })}
            className="rounded-sm num" data-testid="recurring-amount" /></div>
        <div><Label className="overline">Start month (YYYY-MM)</Label>
          <Input value={f.start_month} onChange={(e) => setF({ ...f, start_month: e.target.value })}
            placeholder="2025-07" className="rounded-sm num" data-testid="recurring-start-month" /></div>
        <div className="flex items-end">
          <Button onClick={add} disabled={!f.name.trim()} className="rounded-sm bg-primary text-primary-foreground gap-1.5" data-testid="recurring-add-btn">
            <Plus size={13} /> Create template
          </Button>
        </div>
      </div>
    </Section>
  );
}

function DemoData() {
  const { bump } = useApp();
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/demo/status").then(({ data }) => setStatus(data)).catch(() => setStatus(false));
  useEffect(() => { load(); }, []);

  const run = async (mode) => {
    setBusy(true);
    try {
      if (mode === "load") { const { data } = await api.post("/demo/load"); toast.success(data.message); }
      else { const { data } = await api.delete("/demo/purge"); toast.success(`${data.deleted} demo records removed`); }
      load(); bump();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Section title="Demo data" testId="demo-settings">
      <div className="p-4 space-y-4 max-w-2xl">
        <p className="text-sm text-muted-foreground">
          Demo data is for testing and demonstration only. It seeds FY 2025-26 with Shopify-style sales,
          refunds, Facebook / Google / Snapchat ads, inventory purchases with landed costs, shipping,
          packaging, electricity, software, a machinery purchase, GST across several treatments, a
          missing receipt and a deliberately missing monthly expense.
        </p>
        <div className="border border-border p-3 flex items-center justify-between">
          <div>
            <div className="overline">Status</div>
            <div className="num text-sm mt-1">
              {status?.has_demo_data ? `${status.demo_transaction_count} demo transactions loaded` : "No demo data loaded"}
            </div>
          </div>
          <Pill tone={status?.has_demo_data ? "warning" : "positive"} testId="demo-status-pill">
            {status?.has_demo_data ? "Demo data present" : "Clean"}
          </Pill>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => run("load")} disabled={busy} className="rounded-sm bg-primary text-primary-foreground gap-1.5" data-testid="load-demo-btn">
            <Database size={14} /> {busy ? "Working…" : "Load Demo Data"}
          </Button>
          <Button onClick={() => run("purge")} disabled={busy || !status?.has_demo_data} variant="outline"
            className="rounded-sm text-negative gap-1.5" data-testid="purge-demo-btn">
            <Trash2 size={14} /> Remove Demo Data
          </Button>
        </div>
        <Disclaimer>Every demo record is tagged <span className="num">demo</span> and removable in one click. Real records are never touched.</Disclaimer>
      </div>
    </Section>
  );
}

function Integrations() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/integrations").then(({ data }) => setD(data)).catch(() => setD(false)); }, []);
  if (!d) return <Loading />;
  return (
    <Section title="Integrations" testId="integrations-settings">
      <div className="divide-y divide-border">
        {d.providers.map((p) => (
          <div key={p.provider} className="flex items-center justify-between px-4 py-3" data-testid={`integration-${p.provider}`}>
            <div>
              <div className="text-sm font-semibold">{p.label}</div>
              <div className="overline mt-0.5">Not connected</div>
            </div>
            <Pill tone="warning">{p.phase}</Pill>
          </div>
        ))}
      </div>
      <div className="p-4 border-t border-border"><Disclaimer>{d.note}</Disclaimer></div>
    </Section>
  );
}

function Backup() {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { await downloadFile("/backup/export", `urbandotted_backup_${new Date().toISOString().slice(0, 10)}.json`); toast.success("Backup downloaded"); }
    catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Backup &amp; data portability" testId="backup-settings">
      <div className="p-4 space-y-4 max-w-2xl">
        <p className="text-sm text-muted-foreground">
          Export every record for this business as JSON — categories, transactions, inventory, assets,
          documents metadata, recurring templates, reminders and month-end state. You are never locked in.
        </p>
        <div className="flex gap-2">
          <Button onClick={run} disabled={busy} className="rounded-sm bg-primary text-primary-foreground gap-1.5" data-testid="backup-export-btn">
            <Download size={14} /> {busy ? "Preparing…" : "Export all data (JSON)"}
          </Button>
          <Button asChild variant="outline" className="rounded-sm gap-1.5" data-testid="backup-csv-link">
            <a href="#/transactions">Transaction CSV export lives on the Transactions page</a>
          </Button>
        </div>
        <Disclaimer>Restore/import of a full JSON backup is Coming in Phase 5. CSV import is available now.</Disclaimer>
      </div>
    </Section>
  );
}

function AuditLog() {
  const [list, setList] = useState(null);
  useEffect(() => { api.get("/audit-logs?limit=200").then(({ data }) => setList(data)).catch(() => setList(false)); }, []);
  if (!list) return <Loading />;
  return (
    <Section title={`Audit log (last ${list.length} events)`} testId="audit-settings">
      {!list.length ? <Empty title="No audit events yet" /> : (
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["When", "User", "Entity", "Action", "Record"].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {list.map((l) => (
                <TableRow key={l.log_id} data-testid={`audit-row-${l.log_id}`}>
                  <TableCell className="num text-xs whitespace-nowrap">{String(l.at).slice(0, 19).replace("T", " ")}</TableCell>
                  <TableCell className="text-xs">{l.user_email || "—"}</TableCell>
                  <TableCell className="text-xs capitalize">{l.entity?.replace("_", " ")}</TableCell>
                  <TableCell className="text-xs num">{l.action}</TableCell>
                  <TableCell className="text-xs num text-muted-foreground max-w-[220px] truncate">{l.entity_id}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}
