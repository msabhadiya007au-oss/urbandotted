import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errText } from "@/lib/api";
import { PageHeader, Section, Loading, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ArrowLeft, Eye, EyeOff, ShieldAlert } from "lucide-react";

const STATUS_OPTS = [["active", "Active"], ["on_leave", "On Leave"], ["terminated", "Terminated"], ["archived", "Archived"]];
const TYPE_OPTS = [["full_time", "Full Time"], ["part_time", "Part Time"], ["casual", "Casual"], ["contractor_other", "Contractor / Other"]];
const PAY_BASIS = [["hourly", "Hourly"], ["annual_salary", "Annual Salary"], ["monthly_salary", "Monthly Salary"], ["fixed_pay", "Fixed Pay"], ["custom", "Custom"]];
const PAY_FREQ = [["weekly", "Weekly"], ["fortnightly", "Fortnightly"], ["monthly", "Monthly"], ["custom", "Custom"]];

export default function EmployeeProfile() {
  const { employeeId } = useParams();
  const [emp, setEmp] = useState(null);
  const [tab, setTab] = useState("overview");

  const load = async () => {
    try { const { data } = await api.get(`/payroll/employees/${employeeId}`); setEmp(data); }
    catch (e) { toast.error(errText(e)); setEmp(false); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (emp === null) return <Loading label="Loading employee" />;
  if (emp === false) return <div className="text-sm text-muted-foreground">Employee not found. <Link className="underline" to="/payroll/employees">Back</Link></div>;

  return (
    <div data-testid="employee-profile-page">
      <div className="mb-2 -mt-2">
        <Link to="/payroll/employees" className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft size={12} /> Employees
        </Link>
      </div>
      <PageHeader
        title={`${emp.preferred_name || emp.first_name} ${emp.last_name}`}
        subtitle={`${emp.job_title || "Employee"} · ${(emp.employment_type || "").replace("_", " ")}`}
        right={<Pill tone={emp.status === "active" ? "positive" : "neutral"}>{(emp.status || "").replace("_", " ")}</Pill>}
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm bg-muted h-9 flex-wrap h-auto">
          {[["overview", "Overview"], ["employment", "Employment"], ["pay", "Pay Settings"], ["super", "Super"],
            ["tax", "Tax / PAYG"], ["bank", "Bank"], ["leave", "Leave"], ["leave-settings", "Leave Settings"]].map(([k, l]) => (
            <TabsTrigger key={k} value={k} className="rounded-sm text-xs" data-testid={`emp-tab-${k}`}>{l}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="mt-4"><Overview emp={emp} /></TabsContent>
        <TabsContent value="employment" className="mt-4"><Employment emp={emp} onSaved={load} /></TabsContent>
        <TabsContent value="pay" className="mt-4"><PaySettings employeeId={employeeId} /></TabsContent>
        <TabsContent value="super" className="mt-4"><SuperTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="tax" className="mt-4"><TaxTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="bank" className="mt-4"><BankTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="leave" className="mt-4"><LeaveTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="leave-settings" className="mt-4"><LeaveSettingsTab employeeId={employeeId} /></TabsContent>
      </Tabs>
    </div>
  );
}

function KV({ label, children }) {
  return (
    <div className="border border-border p-3">
      <div className="overline">{label}</div>
      <div className="text-sm mt-1">{children || "—"}</div>
    </div>
  );
}

function Overview({ emp }) {
  return (
    <Section title="Overview" testId="emp-overview">
      <div className="grid gap-3 md:grid-cols-3 p-4">
        <KV label="Email">{emp.email}</KV>
        <KV label="Mobile">{emp.mobile}</KV>
        <KV label="Job title">{emp.job_title}</KV>
        <KV label="Department">{emp.department}</KV>
        <KV label="Start date"><span className="num">{emp.employment_start_date}</span></KV>
        <KV label="Employment type">{(emp.employment_type || "").replace("_", " ")}</KV>
      </div>
    </Section>
  );
}

function Employment({ emp, onSaved }) {
  const [f, setF] = useState(emp);
  const [busy, setBusy] = useState(false);
  useEffect(() => setF(emp), [emp]);
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...f };
      delete payload.employee_id; delete payload.business_id;
      delete payload.created_at; delete payload.created_by;
      delete payload.updated_at; delete payload.updated_by;
      if (!payload.email) delete payload.email;
      await api.put(`/payroll/employees/${emp.employee_id}`, payload);
      toast.success("Employment details saved"); onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Identity & employment" testId="emp-employment">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-4">
        <div><Label className="overline">First name</Label><Input value={f.first_name || ""} onChange={set("first_name")} className="rounded-sm" /></div>
        <div><Label className="overline">Middle name</Label><Input value={f.middle_name || ""} onChange={set("middle_name")} className="rounded-sm" /></div>
        <div><Label className="overline">Last name</Label><Input value={f.last_name || ""} onChange={set("last_name")} className="rounded-sm" /></div>
        <div><Label className="overline">Preferred name</Label><Input value={f.preferred_name || ""} onChange={set("preferred_name")} className="rounded-sm" /></div>
        <div><Label className="overline">Email</Label><Input type="email" value={f.email || ""} onChange={set("email")} className="rounded-sm" /></div>
        <div><Label className="overline">Mobile</Label><Input value={f.mobile || ""} onChange={set("mobile")} className="rounded-sm" /></div>
        <div><Label className="overline">DOB</Label><Input type="date" value={f.dob || ""} onChange={set("dob")} className="rounded-sm num" /></div>
        <div><Label className="overline">Start date</Label><Input type="date" value={f.employment_start_date || ""} onChange={set("employment_start_date")} className="rounded-sm num" /></div>
        <div><Label className="overline">End date</Label><Input type="date" value={f.employment_end_date || ""} onChange={set("employment_end_date")} className="rounded-sm num" /></div>
        <div><Label className="overline">Job title</Label><Input value={f.job_title || ""} onChange={set("job_title")} className="rounded-sm" /></div>
        <div><Label className="overline">Department</Label><Input value={f.department || ""} onChange={set("department")} className="rounded-sm" /></div>
        <div><Label className="overline">Location</Label><Input value={f.location || ""} onChange={set("location")} className="rounded-sm" /></div>
        <div><Label className="overline">Manager</Label><Input value={f.manager || ""} onChange={set("manager")} className="rounded-sm" /></div>
        <div><Label className="overline">Award</Label><Input value={f.award || ""} onChange={set("award")} className="rounded-sm" /></div>
        <div><Label className="overline">Classification</Label><Input value={f.classification || ""} onChange={set("classification")} className="rounded-sm" /></div>
        <div><Label className="overline">Employment type</Label>
          <Select value={f.employment_type} onValueChange={set("employment_type")}>
            <SelectTrigger className="rounded-sm text-xs"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">{TYPE_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select></div>
        <div><Label className="overline">Status</Label>
          <Select value={f.status} onValueChange={set("status")}>
            <SelectTrigger className="rounded-sm text-xs"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">{STATUS_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select></div>
        <div className="sm:col-span-2 lg:col-span-3">
          <Button onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="emp-save">
            {busy ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>
    </Section>
  );
}

function PaySettings({ employeeId }) {
  const [list, setList] = useState(null);
  const [f, setF] = useState({
    pay_basis: "hourly", pay_frequency: "fortnightly",
    base_hourly_rate: "0", annual_salary: "0", monthly_salary: "0", fixed_pay_amount: "0",
    std_hours_per_day: "0", std_hours_per_week: "0", std_hours_per_fortnight: "0",
    std_hours_per_month: "0", std_working_days: "0", effective_from: "", notes: "",
  });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { const { data } = await api.get(`/payroll/employees/${employeeId}/pay-settings`); setList(data.items || []); }
    catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    if (!f.effective_from) { toast.error("Effective-from date is required"); return; }
    setBusy(true);
    try {
      await api.post(`/payroll/employees/${employeeId}/pay-settings`, f);
      toast.success("New pay-settings row created"); load();
      setF({ ...f, effective_from: "" });
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));

  return (
    <Section title="Pay settings history" testId="emp-pay-settings">
      <Disclaimer>Adding a new row caps the previous row's effective-to date. Historical pay runs retain the rate that applied at their pay period.</Disclaimer>
      {list && list.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["From", "To", "Basis", "Freq", "Rate", "Salary", "Std hours/wk"].map((h) =>
                <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {list.map((r) => (
                <TableRow key={r.pay_setting_id}>
                  <TableCell className="text-xs num">{r.effective_from}</TableCell>
                  <TableCell className="text-xs num">{r.effective_to || "current"}</TableCell>
                  <TableCell className="text-xs capitalize">{(r.pay_basis || "").replace("_", " ")}</TableCell>
                  <TableCell className="text-xs capitalize">{r.pay_frequency}</TableCell>
                  <TableCell className="text-xs num">{r.base_hourly_rate || "0"}</TableCell>
                  <TableCell className="text-xs num">{r.annual_salary || r.monthly_salary || "0"}</TableCell>
                  <TableCell className="text-xs num">{r.std_hours_per_week || "0"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <div className="p-4 border-t border-border grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div><Label className="overline">Effective from</Label>
          <Input type="date" value={f.effective_from} onChange={set("effective_from")} className="rounded-sm num" data-testid="pay-effective-from" /></div>
        <div><Label className="overline">Pay basis</Label>
          <Select value={f.pay_basis} onValueChange={set("pay_basis")}>
            <SelectTrigger className="rounded-sm text-xs" data-testid="pay-basis"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">{PAY_BASIS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select></div>
        <div><Label className="overline">Frequency</Label>
          <Select value={f.pay_frequency} onValueChange={set("pay_frequency")}>
            <SelectTrigger className="rounded-sm text-xs"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-popover">{PAY_FREQ.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
          </Select></div>
        <div><Label className="overline">Hourly rate</Label>
          <Input type="number" step="0.01" value={f.base_hourly_rate} onChange={set("base_hourly_rate")} className="rounded-sm num" data-testid="pay-hourly-rate" /></div>
        <div><Label className="overline">Annual salary</Label>
          <Input type="number" step="0.01" value={f.annual_salary} onChange={set("annual_salary")} className="rounded-sm num" /></div>
        <div><Label className="overline">Monthly salary</Label>
          <Input type="number" step="0.01" value={f.monthly_salary} onChange={set("monthly_salary")} className="rounded-sm num" /></div>
        <div><Label className="overline">Fixed pay</Label>
          <Input type="number" step="0.01" value={f.fixed_pay_amount} onChange={set("fixed_pay_amount")} className="rounded-sm num" /></div>
        <div><Label className="overline">Std hours/week</Label>
          <Input type="number" step="0.01" value={f.std_hours_per_week} onChange={set("std_hours_per_week")} className="rounded-sm num" /></div>
        <div className="sm:col-span-2 lg:col-span-4">
          <Button onClick={submit} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="pay-submit">
            {busy ? "Adding…" : "Add pay-settings row"}
          </Button>
        </div>
      </div>
    </Section>
  );
}

function SuperTab({ employeeId }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get(`/payroll/employees/${employeeId}/super`).then(({ data }) => setF({
      super_enabled: true, fund_name: "", member_number: "", usi: "", fund_abn: "",
      fund_source: "employee_nominated", sg_rate: "0.12", additional_employer_pct: "0",
      voluntary_pct: "0", salary_sacrifice_amount: "0", ...(data || {}),
    })).catch(() => setF({ super_enabled: true, sg_rate: "0.12", fund_source: "employee_nominated" }));
  }, [employeeId]);
  if (!f) return <Loading />;
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...f }; delete payload.business_id; delete payload.employee_id;
      delete payload.updated_at; delete payload.updated_by;
      await api.put(`/payroll/employees/${employeeId}/super`, payload);
      toast.success("Super profile saved");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Superannuation profile" testId="emp-super">
      <div className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="flex items-center gap-3">
          <Switch checked={!!f.super_enabled} onCheckedChange={(v) => setF({ ...f, super_enabled: v })} data-testid="super-enabled" />
          <span className="text-xs">Super enabled</span>
        </div>
        <div><Label className="overline">Fund name</Label><Input value={f.fund_name || ""} onChange={set("fund_name")} className="rounded-sm" data-testid="super-fund" /></div>
        <div><Label className="overline">Member number</Label><Input value={f.member_number || ""} onChange={set("member_number")} className="rounded-sm num" /></div>
        <div><Label className="overline">USI</Label><Input value={f.usi || ""} onChange={set("usi")} className="rounded-sm num" /></div>
        <div><Label className="overline">Fund ABN</Label><Input value={f.fund_abn || ""} onChange={set("fund_abn")} className="rounded-sm num" /></div>
        <div><Label className="overline">SG rate (decimal, e.g. 0.12)</Label><Input value={f.sg_rate || ""} onChange={set("sg_rate")} className="rounded-sm num" data-testid="super-rate" /></div>
        <div><Label className="overline">Additional employer %</Label><Input value={f.additional_employer_pct || "0"} onChange={set("additional_employer_pct")} className="rounded-sm num" /></div>
        <div><Label className="overline">Voluntary %</Label><Input value={f.voluntary_pct || "0"} onChange={set("voluntary_pct")} className="rounded-sm num" /></div>
        <div><Label className="overline">Salary sacrifice ($/pay)</Label><Input value={f.salary_sacrifice_amount || "0"} onChange={set("salary_sacrifice_amount")} className="rounded-sm num" /></div>
        <div className="sm:col-span-2 lg:col-span-3">
          <Button onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="super-save">
            {busy ? "Saving…" : "Save super profile"}
          </Button>
        </div>
      </div>
    </Section>
  );
}

function TaxTab({ employeeId }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  useEffect(() => {
    api.get(`/payroll/employees/${employeeId}/tax`)
      .then(({ data }) => setF({
        payg_enabled: true, tax_free_threshold: true, australian_resident: true,
        help_loan: false, other_withholding_pct: "0", manual_payg_override: "0",
        notes: "", ...(data || {}),
      }))
      .catch((e) => {
        if (e?.response?.status === 403) setForbidden(true);
        else toast.error(errText(e));
      });
  }, [employeeId]);
  if (forbidden) return <div className="text-xs text-muted-foreground p-6"><ShieldAlert size={12} className="inline mr-1" /> Only the business owner can view tax / PAYG settings.</div>;
  if (!f) return <Loading />;
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...f }; delete payload.business_id; delete payload.employee_id;
      delete payload.updated_at; delete payload.updated_by;
      await api.put(`/payroll/employees/${employeeId}/tax`, payload);
      toast.success("Tax settings saved");
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Tax / PAYG (owner only)" testId="emp-tax">
      <Disclaimer>PAYG withholding requires verified Australian tax settings. Review before finalising pay.</Disclaimer>
      <div className="p-4 grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-3"><Switch checked={!!f.payg_enabled} onCheckedChange={(v) => setF({ ...f, payg_enabled: v })} data-testid="tax-payg" /><span className="text-xs">PAYG withholding enabled</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.tax_free_threshold} onCheckedChange={(v) => setF({ ...f, tax_free_threshold: v })} data-testid="tax-tft" /><span className="text-xs">Claiming tax-free threshold</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.australian_resident} onCheckedChange={(v) => setF({ ...f, australian_resident: v })} /><span className="text-xs">Australian resident for tax</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.help_loan} onCheckedChange={(v) => setF({ ...f, help_loan: v })} /><span className="text-xs">HELP/Study loan</span></div>
        <div><Label className="overline">Other withholding %</Label><Input value={f.other_withholding_pct} onChange={set("other_withholding_pct")} className="rounded-sm num" /></div>
        <div><Label className="overline">Default manual PAYG per pay ($)</Label><Input value={f.manual_payg_override} onChange={set("manual_payg_override")} className="rounded-sm num" data-testid="tax-manual" /></div>
        <div className="sm:col-span-2"><Label className="overline">Notes</Label><Input value={f.notes || ""} onChange={set("notes")} className="rounded-sm" /></div>
        <div className="sm:col-span-2">
          <Button onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="tax-save">
            {busy ? "Saving…" : "Save tax settings"}
          </Button>
        </div>
      </div>
    </Section>
  );
}

function BankTab({ employeeId }) {
  const [f, setF] = useState({ account_name: "", bsb: "", account_number: "", payment_reference: "" });
  const [masked, setMasked] = useState(null);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  const load = async (revealAll = false) => {
    try {
      const { data } = await api.get(`/payroll/employees/${employeeId}/bank${revealAll ? "?reveal=true" : ""}`);
      setMasked(data);
      if (revealAll) setF({
        account_name: data.account_name || "", bsb: data.bsb || "",
        account_number: data.account_number || "", payment_reference: data.payment_reference || "",
      });
      else setF((p) => ({ ...p, account_name: data.account_name || "", payment_reference: data.payment_reference || "" }));
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else toast.error(errText(e));
    }
  };
  useEffect(() => { load(false); }, [employeeId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (forbidden) return <div className="text-xs text-muted-foreground p-6"><ShieldAlert size={12} className="inline mr-1" /> Only the business owner can view bank details.</div>;

  const toggleReveal = async () => {
    if (!reveal) await load(true);
    setReveal(!reveal);
  };
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/payroll/employees/${employeeId}/bank`, f);
      toast.success("Bank details encrypted & saved");
      setReveal(false); await load(false);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Section title="Bank details (owner only, encrypted)" testId="emp-bank"
      right={<Button size="sm" variant="outline" className="rounded-sm text-xs gap-1.5" onClick={toggleReveal} data-testid="bank-reveal">
        {reveal ? <><EyeOff size={12} /> Hide</> : <><Eye size={12} /> Reveal</>}
      </Button>}>
      <Disclaimer>Full BSB and account number are encrypted at rest using PAYROLL_ENC_KEY. Access is logged in the audit log.</Disclaimer>
      <div className="p-4 grid gap-3 sm:grid-cols-2">
        <div><Label className="overline">Account name</Label><Input value={f.account_name} onChange={set("account_name")} className="rounded-sm" data-testid="bank-name" /></div>
        <div><Label className="overline">Payment reference</Label><Input value={f.payment_reference} onChange={set("payment_reference")} className="rounded-sm" /></div>
        <div><Label className="overline">BSB {!reveal && masked?.bsb_masked && <span className="num text-muted-foreground ml-1">{masked.bsb_masked}</span>}</Label>
          <Input value={reveal ? f.bsb : ""} placeholder={masked?.bsb_masked || "062-000"} onChange={set("bsb")} className="rounded-sm num" data-testid="bank-bsb" disabled={!reveal && masked?.has_details} /></div>
        <div><Label className="overline">Account number {!reveal && masked?.account_number_masked && <span className="num text-muted-foreground ml-1">{masked.account_number_masked}</span>}</Label>
          <Input value={reveal ? f.account_number : ""} placeholder={masked?.account_number_masked || "12345678"} onChange={set("account_number")} className="rounded-sm num" data-testid="bank-account" disabled={!reveal && masked?.has_details} /></div>
        <div className="sm:col-span-2">
          <Button onClick={save} disabled={busy || (!reveal && masked?.has_details)} className="rounded-sm bg-primary text-primary-foreground" data-testid="bank-save">
            {busy ? "Saving…" : "Save bank details"}
          </Button>
          {(!reveal && masked?.has_details) && <span className="ml-3 text-xs text-muted-foreground">Reveal first to edit BSB/account number.</span>}
        </div>
      </div>
    </Section>
  );
}

function LeaveSettingsTab({ employeeId }) {
  const [f, setF] = useState({ accruals: [], notes: "" });
  const [busy, setBusy] = useState(false);
  const load = async () => {
    try { const { data } = await api.get(`/payroll/employees/${employeeId}/leave-settings`); setF({ accruals: data.accruals || [], notes: data.notes || "" }); }
    catch (e) { toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line

  const upd = (i, k, v) => setF((p) => ({ ...p, accruals: p.accruals.map((a, idx) => idx === i ? { ...a, [k]: v } : a) }));
  const add = () => setF((p) => ({ ...p, accruals: [...p.accruals, { leave_type: "annual", hours_per_pay_period: "0", opening_balance_hours: "0", active: true }] }));
  const del = (i) => setF((p) => ({ ...p, accruals: p.accruals.filter((_, idx) => idx !== i) }));

  const save = async () => {
    setBusy(true);
    try {
      await api.put(`/payroll/employees/${employeeId}/leave-settings`, f);
      toast.success("Leave settings saved");
      load();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Section title="Leave accrual settings (per employee)" testId="emp-leave-settings">
      <Disclaimer>Configure how much this employee accrues each pay period, per leave type. Casual employees do not accrue unless you explicitly set a rate here. Accruals post automatically when a pay run is finalised — historical balances are never rewritten.</Disclaimer>
      <div className="p-4 space-y-3">
        {f.accruals.length === 0 && <p className="text-sm text-muted-foreground">No leave accruals configured. Add one to start accruing hours on each finalised pay run.</p>}
        {f.accruals.map((a, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-5 border border-border p-3" data-testid={`leave-accrual-row-${i}`}>
            <div><Label className="overline">Leave type</Label>
              <Input value={a.leave_type} onChange={(e) => upd(i, "leave_type", e.target.value)} className="rounded-sm" data-testid={`leave-accrual-type-${i}`} /></div>
            <div><Label className="overline">Hours / pay period</Label>
              <Input type="number" step="0.0001" value={a.hours_per_pay_period}
                onChange={(e) => upd(i, "hours_per_pay_period", e.target.value)} className="rounded-sm num" data-testid={`leave-accrual-hrs-${i}`} /></div>
            <div><Label className="overline">Opening balance (h)</Label>
              <Input type="number" step="0.0001" value={a.opening_balance_hours}
                onChange={(e) => upd(i, "opening_balance_hours", e.target.value)} className="rounded-sm num" /></div>
            <div className="flex items-center gap-2 mt-6">
              <Switch checked={!!a.active} onCheckedChange={(v) => upd(i, "active", v)} />
              <span className="text-xs">Active</span>
            </div>
            <div className="mt-6">
              <Button size="sm" variant="outline" className="rounded-sm text-xs h-8" onClick={() => del(i)} data-testid={`leave-accrual-del-${i}`}>Remove</Button>
            </div>
          </div>
        ))}
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="rounded-sm text-xs" onClick={add} data-testid="leave-accrual-add">Add accrual row</Button>
          <Button size="sm" className="rounded-sm bg-primary text-primary-foreground text-xs" onClick={save} disabled={busy} data-testid="leave-settings-save">
            {busy ? "Saving…" : "Save leave settings"}
          </Button>
        </div>
      </div>
    </Section>
  );
}

function LeaveTab({ employeeId }) {
  const [list, setList] = useState(null);
  const [f, setF] = useState({ leave_type: "annual", entitled_hours: "0", future_approved_hours: "0", remaining_hours: "0" });
  const load = async () => {
    try { const { data } = await api.get(`/payroll/employees/${employeeId}/leave-balances`); setList(data.items || []); }
    catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    try {
      const { leave_type, ...body } = f;
      await api.put(`/payroll/employees/${employeeId}/leave-balances/${encodeURIComponent(leave_type)}`, { leave_type, ...body });
      toast.success("Leave balance saved"); load();
    } catch (e) { toast.error(errText(e)); }
  };
  return (
    <Section title="Leave balances" testId="emp-leave">
      <Disclaimer>Balances are snapshots. Immutable leave-transaction ledger arrives in Phase 4 (won't rewrite historical balances).</Disclaimer>
      {list && list.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Type", "Entitled (h)", "Future approved (h)", "Remaining (h)"].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {list.map((r) => (
                <TableRow key={r.leave_type}>
                  <TableCell className="text-xs capitalize">{r.leave_type}</TableCell>
                  <TableCell className="text-xs num">{r.entitled_hours}</TableCell>
                  <TableCell className="text-xs num">{r.future_approved_hours}</TableCell>
                  <TableCell className="text-xs num">{r.remaining_hours}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <div className="p-4 border-t border-border grid gap-3 sm:grid-cols-4">
        <div><Label className="overline">Leave type</Label><Input value={f.leave_type} onChange={set("leave_type")} className="rounded-sm" data-testid="leave-type" /></div>
        <div><Label className="overline">Entitled hours</Label><Input value={f.entitled_hours} onChange={set("entitled_hours")} className="rounded-sm num" /></div>
        <div><Label className="overline">Future approved</Label><Input value={f.future_approved_hours} onChange={set("future_approved_hours")} className="rounded-sm num" /></div>
        <div><Label className="overline">Remaining</Label><Input value={f.remaining_hours} onChange={set("remaining_hours")} className="rounded-sm num" /></div>
        <div className="sm:col-span-4">
          <Button onClick={save} className="rounded-sm bg-primary text-primary-foreground" data-testid="leave-save">Save leave balance</Button>
        </div>
      </div>
    </Section>
  );
}
