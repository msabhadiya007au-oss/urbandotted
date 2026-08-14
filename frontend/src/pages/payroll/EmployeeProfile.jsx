import React, { useEffect, useState } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api, errText } from "@/lib/api";
import { PageHeader, Section, Loading, Pill, Disclaimer, Empty } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, Eye, EyeOff, ShieldAlert, UserX, UserPlus, Upload, Trash2, Download } from "lucide-react";

const STATUS_OPTS = [["active", "Active"], ["on_leave", "On Leave"], ["terminated", "Terminated"], ["archived", "Archived"]];
const TYPE_OPTS = [["full_time", "Full Time"], ["part_time", "Part Time"], ["casual", "Casual"], ["contractor_other", "Contractor / Other"]];
const PAY_BASIS = [["hourly", "Hourly"], ["annual_salary", "Annual Salary"], ["monthly_salary", "Monthly Salary"], ["fixed_pay", "Fixed Pay"], ["custom", "Custom"]];
const PAY_FREQ = [["weekly", "Weekly"], ["fortnightly", "Fortnightly"], ["monthly", "Monthly"], ["custom", "Custom"]];

export default function EmployeeProfile() {
  const { employeeId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [emp, setEmp] = useState(null);
  const [tab, setTab] = useState("overview");
  const [termOpen, setTermOpen] = useState(false);
  const [rehireOpen, setRehireOpen] = useState(false);

  const load = async () => {
    try { const { data } = await api.get(`/payroll/employees/${employeeId}`); setEmp(data); }
    catch (e) { toast.error(errText(e)); setEmp(false); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (emp && searchParams.get("action") === "rehire" && emp.status === "terminated") {
      setRehireOpen(true);
      searchParams.delete("action"); setSearchParams(searchParams, { replace: true });
    }
  }, [emp]); // eslint-disable-line

  if (emp === null) return <Loading label="Loading employee" />;
  if (emp === false) return <div className="text-sm text-muted-foreground">Employee not found. <Link className="underline" to="/payroll/employees">Back</Link></div>;

  const canTerminate = emp.status === "active" || emp.status === "on_leave";
  const canRehire = emp.status === "terminated";

  return (
    <div data-testid="employee-profile-page">
      <div className="mb-2 -mt-2">
        <Link to="/payroll/employees" className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft size={12} /> Employees
        </Link>
      </div>
      <PageHeader
        title={`${emp.preferred_name || emp.first_name} ${emp.last_name}`}
        subtitle={`${emp.job_title || "Employee"} · ${(emp.employment_type || "").replace("_", " ")} · ID ${(emp.employee_id || "").replace("emp_", "").slice(0, 8).toUpperCase()}`}
        children={
          <div className="flex items-center gap-2">
            <Pill tone={emp.status === "active" ? "positive" : emp.status === "terminated" ? "negative" : "warning"}>{(emp.status || "").replace("_", " ")}</Pill>
            {canTerminate && (
              <Button size="sm" variant="outline" className="rounded-sm text-xs gap-1"
                onClick={() => setTermOpen(true)} data-testid="terminate-btn"><UserX size={12} /> Terminate</Button>
            )}
            {canRehire && (
              <Button size="sm" className="rounded-sm text-xs gap-1 bg-primary text-primary-foreground"
                onClick={() => setRehireOpen(true)} data-testid="rehire-btn"><UserPlus size={12} /> Rehire</Button>
            )}
          </div>
        }
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="rounded-sm bg-muted h-auto flex-wrap">
          {[["overview", "Overview"], ["employment", "Employment"], ["pay", "Pay Settings"], ["super", "Super"],
            ["tax", "Tax / PAYG"], ["bank", "Bank"], ["leave", "Leave"], ["leave-settings", "Leave Settings"],
            ["documents", "Documents & Notes"], ["history", "History"]].map(([k, l]) => (
            <TabsTrigger key={k} value={k} className="rounded-sm text-xs" data-testid={`emp-tab-${k}`}>{l}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="mt-4"><Overview emp={emp} onSaved={load} /></TabsContent>
        <TabsContent value="employment" className="mt-4"><Employment emp={emp} onSaved={load} /></TabsContent>
        <TabsContent value="pay" className="mt-4"><PaySettings employeeId={employeeId} /></TabsContent>
        <TabsContent value="super" className="mt-4"><SuperTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="tax" className="mt-4"><TaxTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="bank" className="mt-4"><BankTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="leave" className="mt-4"><LeaveTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="leave-settings" className="mt-4"><LeaveSettingsTab employeeId={employeeId} /></TabsContent>
        <TabsContent value="documents" className="mt-4"><DocumentsTab employeeId={employeeId} emp={emp} onSaved={load} /></TabsContent>
        <TabsContent value="history" className="mt-4"><HistoryTab employeeId={employeeId} /></TabsContent>
      </Tabs>

      {termOpen && <TerminateDialog emp={emp} onClose={() => setTermOpen(false)} onSaved={() => { setTermOpen(false); load(); }} />}
      {rehireOpen && <RehireDialog emp={emp} onClose={() => setRehireOpen(false)} onSaved={() => { setRehireOpen(false); load(); }} />}
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

function Overview({ emp, onSaved }) {
  const [f, setF] = useState(emp);
  const [busy, setBusy] = useState(false);
  useEffect(() => setF(emp), [emp]);
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const setBool = (k) => (v) => setF((p) => ({ ...p, [k]: v }));

  const save = async () => {
    setBusy(true);
    try {
      const payload = { ...f };
      ["employee_id", "business_id", "created_at", "created_by", "updated_at", "updated_by",
       "is_deleted", "employment_periods", "termination_reason", "termination_note",
       "terminated_at", "terminated_by", "document_ids", "current_pay_basis",
       "current_pay_frequency"].forEach((k) => delete payload[k]);
      if (!payload.email) delete payload.email;
      await api.put(`/payroll/employees/${emp.employee_id}`, payload);
      toast.success("Profile saved");
      onSaved && onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      <Section title="Personal details" testId="emp-overview-personal">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-4">
          <TxtField label="Legal first name *" v={f.first_name} onChange={set("first_name")} testid="ov-first" />
          <TxtField label="Middle name" v={f.middle_name} onChange={set("middle_name")} />
          <TxtField label="Legal last name *" v={f.last_name} onChange={set("last_name")} testid="ov-last" />
          <TxtField label="Preferred name" v={f.preferred_name} onChange={set("preferred_name")} testid="ov-preferred" />
          <DateField label="Date of birth" v={f.dob} onChange={set("dob")} testid="ov-dob" />
          <div />
          <TxtField label="Personal email" type="email" v={f.email} onChange={set("email")} testid="ov-email" />
          <TxtField label="Work email" type="email" v={f.work_email} onChange={set("work_email")} testid="ov-work-email" />
          <div />
          <TxtField label="Mobile" v={f.mobile} onChange={set("mobile")} testid="ov-mobile" />
          <TxtField label="Alternative phone" v={f.alt_phone} onChange={set("alt_phone")} />
        </div>
      </Section>

      <Section title="Residential address" testId="emp-overview-residential">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-4">
          <TxtField label="Address line 1" v={f.address} onChange={set("address")} testid="ov-addr1" />
          <TxtField label="Address line 2" v={f.address_line_2} onChange={set("address_line_2")} />
          <TxtField label="Suburb" v={f.suburb} onChange={set("suburb")} testid="ov-suburb" />
          <TxtField label="State" v={f.state} onChange={set("state")} testid="ov-state" />
          <TxtField label="Postcode" v={f.postcode} onChange={set("postcode")} testid="ov-postcode" />
          <TxtField label="Country" v={f.country} onChange={set("country")} />
        </div>
      </Section>

      <Section title="Postal address" testId="emp-overview-postal">
        <div className="p-4">
          <div className="flex items-center gap-3 mb-3">
            <Switch checked={!!f.postal_same_as_residential} onCheckedChange={setBool("postal_same_as_residential")} data-testid="ov-postal-same" />
            <span className="text-xs">Same as residential address</span>
          </div>
          {!f.postal_same_as_residential && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <TxtField label="Postal address line 1" v={f.postal_address} onChange={set("postal_address")} testid="ov-postal-addr1" />
              <TxtField label="Postal address line 2" v={f.postal_address_line_2} onChange={set("postal_address_line_2")} />
              <TxtField label="Postal suburb" v={f.postal_suburb} onChange={set("postal_suburb")} />
              <TxtField label="Postal state" v={f.postal_state} onChange={set("postal_state")} />
              <TxtField label="Postal postcode" v={f.postal_postcode} onChange={set("postal_postcode")} />
              <TxtField label="Postal country" v={f.postal_country} onChange={set("postal_country")} />
            </div>
          )}
        </div>
      </Section>

      <Section title="Emergency contact" testId="emp-overview-emergency">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 p-4">
          <TxtField label="Name" v={f.emergency_contact_name} onChange={set("emergency_contact_name")} testid="ov-ec-name" />
          <TxtField label="Relationship" v={f.emergency_contact_relationship} onChange={set("emergency_contact_relationship")} />
          <TxtField label="Mobile" v={f.emergency_contact_mobile} onChange={set("emergency_contact_mobile")} testid="ov-ec-mobile" />
          <TxtField label="Alternative phone" v={f.emergency_contact_alt_phone} onChange={set("emergency_contact_alt_phone")} />
        </div>
      </Section>

      <Section title="Current employment summary" testId="emp-overview-summary">
        <div className="grid gap-3 md:grid-cols-3 p-4">
          <KV label="Status">{(emp.status || "").replace("_", " ")}</KV>
          <KV label="Start date"><span className="num">{emp.employment_start_date}</span></KV>
          <KV label="Job title">{emp.job_title}</KV>
          <KV label="Employment type">{(emp.employment_type || "").replace("_", " ")}</KV>
          <KV label="Pay basis">{emp.current_pay_basis || "—"}</KV>
          <KV label="Pay frequency">{emp.current_pay_frequency || "—"}</KV>
        </div>
      </Section>

      <div>
        <Button onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="ov-save">
          {busy ? "Saving…" : "Save personal details"}
        </Button>
      </div>
    </div>
  );
}

function TxtField({ label, v, onChange, type = "text", testid }) {
  return (
    <div>
      <Label className="overline">{label}</Label>
      <Input type={type} value={v ?? ""} onChange={onChange} className="rounded-sm" data-testid={testid} />
    </div>
  );
}
function DateField({ label, v, onChange, testid }) {
  return (
    <div>
      <Label className="overline">{label}</Label>
      <Input type="date" value={v ?? ""} onChange={onChange} className="rounded-sm num" data-testid={testid} />
    </div>
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
      ["employee_id", "business_id", "created_at", "created_by", "updated_at", "updated_by",
       "is_deleted", "employment_periods", "termination_reason", "termination_note",
       "terminated_at", "terminated_by", "document_ids", "current_pay_basis",
       "current_pay_frequency"].forEach((k) => delete payload[k]);
      if (!payload.email) delete payload.email;
      await api.put(`/payroll/employees/${emp.employee_id}`, payload);
      toast.success("Employment details saved"); onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <Section title="Employment details" testId="emp-employment">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-4">
          <div><Label className="overline">Employment type</Label>
            <Select value={f.employment_type} onValueChange={set("employment_type")}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="emp-type-select"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">{TYPE_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select></div>
          <div><Label className="overline">Status</Label>
            <Select value={f.status} onValueChange={set("status")}>
              <SelectTrigger className="rounded-sm text-xs"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">{STATUS_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select></div>
          <TxtField label="Job title" v={f.job_title} onChange={set("job_title")} testid="emp-job" />
          <TxtField label="Department" v={f.department} onChange={set("department")} />
          <TxtField label="Location / Workplace" v={f.location} onChange={set("location")} />
          <TxtField label="Manager" v={f.manager} onChange={set("manager")} />
          <TxtField label="Award" v={f.award} onChange={set("award")} />
          <TxtField label="Classification" v={f.classification} onChange={set("classification")} />
          <DateField label="Start date *" v={f.employment_start_date} onChange={set("employment_start_date")} testid="emp-start" />
          <DateField label="Probation end date" v={f.probation_end_date} onChange={set("probation_end_date")} testid="emp-probation" />
          <DateField label="End date" v={f.employment_end_date} onChange={set("employment_end_date")} />
        </div>
      </Section>

      <Section title="Ordinary working arrangement" testId="emp-work-arrangement">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 p-4">
          <TxtField label="Std hours per day" v={f.std_hours_per_day} onChange={set("std_hours_per_day")} testid="emp-hrs-day" />
          <TxtField label="Std hours per week" v={f.std_hours_per_week} onChange={set("std_hours_per_week")} testid="emp-hrs-week" />
          <TxtField label="Std hours per fortnight" v={f.std_hours_per_fortnight} onChange={set("std_hours_per_fortnight")} testid="emp-hrs-fn" />
          <TxtField label="Std hours per month" v={f.std_hours_per_month} onChange={set("std_hours_per_month")} testid="emp-hrs-month" />
          <TxtField label="Working days per week" v={f.std_working_days} onChange={set("std_working_days")} testid="emp-working-days" />
        </div>
      </Section>

      <Section title="Optional weekly work pattern (hours per day)" testId="emp-pattern">
        <div className="p-4">
          <p className="text-[11px] text-muted-foreground mb-3">Leave zero if this employee does not have a fixed daily pattern.</p>
          <div className="grid gap-2 grid-cols-7">
            {["mon","tue","wed","thu","fri","sat","sun"].map((d) => (
              <div key={d}>
                <Label className="overline capitalize">{d}</Label>
                <Input type="number" step="0.25" value={f[`pattern_${d}_hours`] ?? "0"}
                  onChange={(e) => setF({ ...f, [`pattern_${d}_hours`]: e.target.value })}
                  className="rounded-sm num" data-testid={`emp-pattern-${d}`} />
              </div>
            ))}
          </div>
        </div>
      </Section>

      <div><Button onClick={save} disabled={busy} className="rounded-sm bg-primary text-primary-foreground" data-testid="emp-save">
        {busy ? "Saving…" : "Save employment"}
      </Button></div>
    </div>
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
          <Input type="number" step="0.01" value={f.annual_salary} onChange={set("annual_salary")} className="rounded-sm num" data-testid="pay-annual" /></div>
        <div><Label className="overline">Monthly salary</Label>
          <Input type="number" step="0.01" value={f.monthly_salary} onChange={set("monthly_salary")} className="rounded-sm num" /></div>
        <div><Label className="overline">Fixed pay</Label>
          <Input type="number" step="0.01" value={f.fixed_pay_amount} onChange={set("fixed_pay_amount")} className="rounded-sm num" /></div>
        <div><Label className="overline">Std hours/day</Label>
          <Input type="number" step="0.01" value={f.std_hours_per_day} onChange={set("std_hours_per_day")} className="rounded-sm num" /></div>
        <div><Label className="overline">Std hours/week</Label>
          <Input type="number" step="0.01" value={f.std_hours_per_week} onChange={set("std_hours_per_week")} className="rounded-sm num" data-testid="pay-std-week" /></div>
        <div><Label className="overline">Std hours/fortnight</Label>
          <Input type="number" step="0.01" value={f.std_hours_per_fortnight} onChange={set("std_hours_per_fortnight")} className="rounded-sm num" /></div>
        <div><Label className="overline">Std hours/month</Label>
          <Input type="number" step="0.01" value={f.std_hours_per_month} onChange={set("std_hours_per_month")} className="rounded-sm num" /></div>
        <div><Label className="overline">Working days</Label>
          <Input type="number" step="0.5" value={f.std_working_days} onChange={set("std_working_days")} className="rounded-sm num" /></div>
        <div className="sm:col-span-2 lg:col-span-4">
          <Textarea value={f.notes || ""} onChange={set("notes")} placeholder="Effective-dated pay note (visible to owner)" className="rounded-sm text-xs min-h-[60px]" />
          <p className="text-[10px] text-muted-foreground mt-1">Adding a new row caps the previous row and never changes historical payslips.</p>
        </div>
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
  const [revealed, setRevealed] = useState(false);

  const load = async (reveal = false) => {
    try {
      const { data } = await api.get(`/payroll/employees/${employeeId}/tax${reveal ? "?reveal_tfn=true" : ""}`);
      setF({
        payg_enabled: true, tax_free_threshold: true, australian_resident: true,
        help_loan: false, other_withholding_pct: "0", manual_payg_override: "0",
        tfn: "", tfn_declared: false, notes: "", ...(data || {}),
      });
      if (reveal) setRevealed(true);
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else toast.error(errText(e));
    }
  };
  useEffect(() => { load(false); }, [employeeId]); // eslint-disable-line
  if (forbidden) return <div className="text-xs text-muted-foreground p-6"><ShieldAlert size={12} className="inline mr-1" /> Only the business owner can view tax / PAYG settings.</div>;
  if (!f) return <Loading />;
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));
  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        payg_enabled: f.payg_enabled, tax_free_threshold: f.tax_free_threshold,
        australian_resident: f.australian_resident, help_loan: f.help_loan,
        other_withholding_pct: f.other_withholding_pct, manual_payg_override: f.manual_payg_override,
        tfn_declared: !!f.tfn_declared, notes: f.notes || "",
        tfn: revealed ? (f.tfn || "") : "",
      };
      await api.put(`/payroll/employees/${employeeId}/tax`, payload);
      toast.success("Tax settings saved");
      setRevealed(false); load(false);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Section title="Tax / PAYG (owner only)" testId="emp-tax"
      right={<Button size="sm" variant="outline" className="rounded-sm text-xs gap-1.5"
        onClick={() => revealed ? (setRevealed(false), load(false)) : load(true)} data-testid="tax-reveal">
        {revealed ? <><EyeOff size={12} /> Hide TFN</> : <><Eye size={12} /> Reveal TFN</>}
      </Button>}>
      <Disclaimer>PAYG withholding is entered manually — verified ATO tax tables are not built into this deployment. Tax File Number is encrypted at rest and never appears in logs.</Disclaimer>
      <div className="p-4 grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-3"><Switch checked={!!f.payg_enabled} onCheckedChange={(v) => setF({ ...f, payg_enabled: v })} data-testid="tax-payg" /><span className="text-xs">PAYG withholding enabled</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.tax_free_threshold} onCheckedChange={(v) => setF({ ...f, tax_free_threshold: v })} data-testid="tax-tft" /><span className="text-xs">Claiming tax-free threshold</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.australian_resident} onCheckedChange={(v) => setF({ ...f, australian_resident: v })} /><span className="text-xs">Australian resident for tax</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.help_loan} onCheckedChange={(v) => setF({ ...f, help_loan: v })} /><span className="text-xs">HELP/Study loan</span></div>
        <div className="flex items-center gap-3"><Switch checked={!!f.tfn_declared} onCheckedChange={(v) => setF({ ...f, tfn_declared: v })} data-testid="tax-tfn-declared" /><span className="text-xs">TFN declaration received</span></div>
        <div />
        <div><Label className="overline">TFN {!revealed && f.tfn_masked && <span className="num text-muted-foreground ml-1">{f.tfn_masked}</span>}</Label>
          <Input value={revealed ? (f.tfn || "") : ""} placeholder={f.tfn_masked || "9 digits"} onChange={set("tfn")}
            className="rounded-sm num" data-testid="tax-tfn" disabled={!revealed && f.has_tfn} />
          {(!revealed && f.has_tfn) && <p className="text-[10px] text-muted-foreground mt-1">Reveal first to edit.</p>}
        </div>
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

// ---------------------------------------------------------------------------
// Documents & Notes tab
// ---------------------------------------------------------------------------
function DocumentsTab({ employeeId, emp, onSaved }) {
  const [docs, setDocs] = useState(null);
  const [notes, setNotes] = useState(emp.notes || "");
  const [savingNotes, setSavingNotes] = useState(false);
  const [uploading, setUploading] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/documents?linked_type=employee&linked_id=${employeeId}`);
      setDocs(data.items || []);
    } catch (e) { setDocs([]); toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [employeeId]); // eslint-disable-line

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("linked_type", "employee");
      fd.append("linked_id", employeeId);
      await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Uploaded");
      load();
    } catch (e) { toast.error(errText(e)); } finally { setUploading(false); }
  };

  const del = async (id) => {
    if (!window.confirm("Delete this document?")) return;
    try { await api.delete(`/documents/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(errText(e)); }
  };

  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      const payload = { ...emp, notes };
      ["employee_id", "business_id", "created_at", "created_by", "updated_at", "updated_by",
       "is_deleted", "employment_periods", "termination_reason", "termination_note",
       "terminated_at", "terminated_by", "document_ids", "current_pay_basis",
       "current_pay_frequency"].forEach((k) => delete payload[k]);
      if (!payload.email) delete payload.email;
      await api.put(`/payroll/employees/${employeeId}`, payload);
      toast.success("Notes saved");
      onSaved && onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setSavingNotes(false); }
  };

  return (
    <div className="space-y-4">
      <Section title="Internal notes" testId="emp-notes">
        <div className="p-4">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes visible only to authorised business users. Never shown to the employee."
            className="rounded-sm min-h-[100px] text-sm" data-testid="emp-notes-input" />
          <Button onClick={saveNotes} disabled={savingNotes} className="rounded-sm bg-primary text-primary-foreground mt-3" data-testid="emp-notes-save">
            {savingNotes ? "Saving…" : "Save notes"}
          </Button>
        </div>
      </Section>

      <Section title="Employment documents" testId="emp-documents"
        right={
          <label className="inline-flex items-center gap-1.5 text-xs cursor-pointer border border-border px-2 py-1 rounded-sm hover:bg-accent/40" data-testid="emp-doc-upload-label">
            <Upload size={12} /> {uploading ? "Uploading…" : "Upload"}
            <input type="file" className="hidden" onChange={(e) => upload(e.target.files?.[0])}
              data-testid="emp-doc-upload-input" />
          </label>
        }>
        <Disclaimer>Documents are private and require authentication. Access is audited. Do not upload files containing sensitive data unless you understand who can access this business account.</Disclaimer>
        {docs === null ? <Loading /> : docs.length === 0 ? (
          <Empty title="No documents yet" hint="Upload contracts, TFN declarations, superannuation forms, etc." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Filename", "Size", "Uploaded", "Notes", ""].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {docs.map((d) => (
                  <TableRow key={d.document_id} data-testid={`emp-doc-${d.document_id}`}>
                    <TableCell className="text-xs">{d.filename}</TableCell>
                    <TableCell className="text-xs num text-muted-foreground">{Math.round((d.size || 0) / 1024)} KB</TableCell>
                    <TableCell className="text-xs num text-muted-foreground">{(d.created_at || "").slice(0, 10)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{d.notes || "—"}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button asChild size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          data-testid={`emp-doc-download-${d.document_id}`}>
                          <a href={`${api.defaults.baseURL}/documents/${d.document_id}/download`} target="_blank" rel="noopener noreferrer">
                            <Download size={11} />
                          </a>
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 text-negative"
                          onClick={() => del(d.document_id)} data-testid={`emp-doc-delete-${d.document_id}`}>
                          <Trash2 size={11} />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Employment history (periods)
// ---------------------------------------------------------------------------
function HistoryTab({ employeeId }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get(`/payroll/employees/${employeeId}/history`).then(({ data }) => setItems(data.periods || []))
      .catch((e) => { setItems([]); toast.error(errText(e)); });
  }, [employeeId]);
  return (
    <Section title="Employment history" testId="emp-history">
      <Disclaimer>Every termination and rehire opens a new employment period. Historical periods and payroll are never deleted or changed.</Disclaimer>
      {items === null ? <Loading /> : items.length === 0 ? (
        <Empty title="No employment periods recorded" hint="Employees created before this feature won't have a period ledger. Periods start on new create/terminate/rehire actions." />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Period", "Start", "End", "Termination reason", "Note", "Rehired"].map((h) =>
                <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {items.map((p, i) => (
                <TableRow key={p.period_id || i} data-testid={`emp-period-${i}`}>
                  <TableCell className="text-xs num">#{i + 1}</TableCell>
                  <TableCell className="text-xs num">{p.start_date || "—"}</TableCell>
                  <TableCell className="text-xs num">{p.end_date || <Pill tone="positive">current</Pill>}</TableCell>
                  <TableCell className="text-xs">{p.termination_reason || "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.termination_note || p.rehire_note || "—"}</TableCell>
                  <TableCell className="text-xs num text-muted-foreground">{p.rehired_at ? p.rehired_at.slice(0, 10) : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Terminate / Rehire dialogs
// ---------------------------------------------------------------------------
function TerminateDialog({ emp, onClose, onSaved }) {
  const [f, setF] = useState({
    termination_date: new Date().toISOString().slice(0, 10),
    reason: "", note: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/payroll/employees/${emp.employee_id}/terminate`, f);
      toast.success("Employee terminated. History preserved.");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="terminate-dialog">
        <DialogHeader><DialogTitle>Terminate employee</DialogTitle></DialogHeader>
        <Disclaimer>Termination never deletes payroll history. It closes the current employment period and moves the employee to the Terminated list.</Disclaimer>
        <div className="grid gap-3 mt-2">
          <div><Label className="overline">Termination date *</Label>
            <Input type="date" value={f.termination_date} onChange={(e) => setF({ ...f, termination_date: e.target.value })}
              className="rounded-sm num" data-testid="terminate-date" /></div>
          <div><Label className="overline">Reason (optional)</Label>
            <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })}
              placeholder="Resignation, redundancy, end of contract…" className="rounded-sm" data-testid="terminate-reason" /></div>
          <div><Label className="overline">Internal note (optional)</Label>
            <Textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })}
              className="rounded-sm text-xs min-h-[70px]" data-testid="terminate-note" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !f.termination_date}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="terminate-submit">
            {busy ? "Saving…" : "Terminate employee"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RehireDialog({ emp, onClose, onSaved }) {
  const [f, setF] = useState({
    start_date: new Date().toISOString().slice(0, 10),
    employment_type: emp.employment_type || "full_time",
    job_title: emp.job_title || "", note: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post(`/payroll/employees/${emp.employee_id}/rehire`, f);
      toast.success("Employee rehired. Previous history preserved.");
      onSaved();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="rehire-dialog">
        <DialogHeader><DialogTitle>Rehire employee</DialogTitle></DialogHeader>
        <Disclaimer>Rehire opens a new employment period. Previous finalised pay runs, payslips, super and YTD remain byte-identical.</Disclaimer>
        <div className="grid gap-3 mt-2">
          <div><Label className="overline">New start date *</Label>
            <Input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })}
              className="rounded-sm num" data-testid="rehire-start-date" /></div>
          <div><Label className="overline">Employment type</Label>
            <Select value={f.employment_type} onValueChange={(v) => setF({ ...f, employment_type: v })}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="rehire-type"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">{TYPE_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
            </Select></div>
          <div><Label className="overline">Job title</Label>
            <Input value={f.job_title} onChange={(e) => setF({ ...f, job_title: e.target.value })}
              className="rounded-sm" data-testid="rehire-title" /></div>
          <div><Label className="overline">Note (optional)</Label>
            <Textarea value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })}
              className="rounded-sm text-xs min-h-[60px]" /></div>
          <p className="text-[11px] text-muted-foreground">Remember to add a new Pay Settings row (Pay Settings tab) to reflect the current rate.</p>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !f.start_date}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="rehire-submit">
            {busy ? "Saving…" : "Rehire employee"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

