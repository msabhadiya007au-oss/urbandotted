import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api, errText } from "@/lib/api";
import { PageHeader, Section, Loading, Empty, Pill } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Search, ExternalLink, AlertTriangle } from "lucide-react";

const STATUS_TONES = {
  active: "positive",
  on_leave: "warning",
  terminated: "neutral",
  archived: "neutral",
};

const STATUS_OPTS = [
  ["active", "Active"], ["on_leave", "On Leave"], ["terminated", "Terminated"], ["archived", "Archived"],
];
const TYPE_OPTS = [
  ["full_time", "Full Time"], ["part_time", "Part Time"], ["casual", "Casual"], ["contractor_other", "Contractor / Other"],
];
const FILTER_OPTS = [
  ["active", "Active"], ["on_leave", "On Leave"], ["terminated", "Terminated"], ["all", "All statuses"],
];

const shortId = (id) => (id ? id.replace("emp_", "").slice(0, 8).toUpperCase() : "—");

export default function Employees() {
  const [list, setList] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("active");
  const [createOpen, setCreateOpen] = useState(false);

  const load = async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status !== "all") params.set("status", status);
    params.set("include_terminated", "true");
    try {
      const { data } = await api.get(`/payroll/employees?${params.toString()}`);
      setList(data.items || []);
    } catch (e) { setList([]); toast.error(errText(e)); }
  };

  useEffect(() => { load(); }, [q, status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div data-testid="employees-page">
      <PageHeader
        title="Employees"
        subtitle="People on Urban Dotted's payroll. Rate, super and bank details live on the employee profile."
        children={
          <Button size="sm" className="rounded-sm bg-primary text-primary-foreground gap-1.5"
            onClick={() => setCreateOpen(true)} data-testid="employee-new-btn">
            <Plus size={14} /> Add Employee
          </Button>
        }
      />

      <Section title={`Directory ${list ? `(${list.length})` : ""}`} testId="employees-directory">
        <div className="px-4 py-3 border-b border-border flex gap-2 flex-wrap items-center">
          <div className="relative flex-1 max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, ID, title…"
              className="pl-8 h-9 rounded-sm text-sm" data-testid="employee-search" />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="employee-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover">
              {FILTER_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {list === null ? <Loading /> : list.length === 0 ? (
          <Empty title="No employees yet" hint="Add your first employee to get started with payroll." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["ID", "Name", "Job title", "Type", "Pay basis", "Pay frequency", "Start date", "Status", ""].map((h) =>
                  <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {list.map((e) => (
                  <TableRow key={e.employee_id} data-testid={`employee-row-${e.employee_id}`}>
                    <TableCell className="text-xs num text-muted-foreground">{shortId(e.employee_id)}</TableCell>
                    <TableCell className="text-xs font-semibold">
                      <Link to={`/payroll/employees/${e.employee_id}`} className="hover:underline">
                        {e.preferred_name || e.first_name} {e.last_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{e.job_title || "—"}</TableCell>
                    <TableCell className="text-xs capitalize">{(e.employment_type || "").replace("_", " ")}</TableCell>
                    <TableCell className="text-xs capitalize">{e.current_pay_basis ? e.current_pay_basis.replace("_", " ") : "—"}</TableCell>
                    <TableCell className="text-xs capitalize">{e.current_pay_frequency || "—"}</TableCell>
                    <TableCell className="text-xs num">{e.employment_start_date || "—"}</TableCell>
                    <TableCell><Pill tone={STATUS_TONES[e.status] || "neutral"}>{(e.status || "").replace("_", " ")}</Pill></TableCell>
                    <TableCell>
                      <Button asChild size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                        data-testid={`employee-view-${e.employee_id}`}>
                        <Link to={`/payroll/employees/${e.employee_id}`}><ExternalLink size={11} /> View</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {createOpen && <CreateEmployeeDialog onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); load(); }} />}
    </div>
  );
}

function CreateEmployeeDialog({ onClose, onCreated }) {
  const navigate = useNavigate();
  const [f, setF] = useState({
    first_name: "", middle_name: "", last_name: "", preferred_name: "",
    dob: "", email: "", mobile: "", employment_type: "full_time", status: "active",
    job_title: "", department: "", employment_start_date: "",
  });
  const [busy, setBusy] = useState(false);
  const [matches, setMatches] = useState(null);   // duplicate-detection UI

  const submit = async ({ force = false } = {}) => {
    setBusy(true);
    try {
      const payload = { ...f };
      if (!payload.email) delete payload.email;
      const url = force ? "/payroll/employees?force=true" : "/payroll/employees";
      const { data } = await api.post(url, payload);
      toast.success(`Added ${data.first_name} ${data.last_name}`);
      onCreated();
      navigate(`/payroll/employees/${data.employee_id}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409 && detail?.code === "possible_duplicate") {
        setMatches(detail.matches || []);
      } else {
        toast.error(errText(e));
      }
    } finally { setBusy(false); }
  };

  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));

  if (matches) {
    return (
      <Dialog open onOpenChange={onClose}>
        <DialogContent className="max-w-lg bg-card" data-testid="duplicate-dialog">
          <DialogHeader><DialogTitle><AlertTriangle size={16} className="inline mr-1 -mt-0.5 text-warning" /> Possible matching employee found</DialogTitle></DialogHeader>
          <p className="text-xs text-muted-foreground">These existing employees look like a match. Please confirm what to do:</p>
          <div className="mt-3 space-y-2 max-h-64 overflow-y-auto">
            {matches.map((m) => (
              <div key={m.employee_id} className="border border-border p-3 flex items-center gap-3" data-testid={`dup-match-${m.employee_id}`}>
                <div className="flex-1">
                  <div className="text-sm font-semibold">{m.preferred_name || m.first_name} {m.last_name}
                    <Pill tone={STATUS_TONES[m.status] || "neutral"}>{(m.status || "").replace("_", " ")}</Pill>
                  </div>
                  <div className="text-[11px] text-muted-foreground num">{shortId(m.employee_id)} · {m.email || "no email"} · {m.mobile || "no mobile"} · started {m.employment_start_date || "—"}</div>
                </div>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" className="rounded-sm text-[10px] h-7 px-2" asChild data-testid={`dup-view-${m.employee_id}`}>
                    <Link to={`/payroll/employees/${m.employee_id}`}>View</Link>
                  </Button>
                  {m.status === "terminated" && (
                    <Button size="sm" variant="outline" className="rounded-sm text-[10px] h-7 px-2" asChild data-testid={`dup-rehire-${m.employee_id}`}>
                      <Link to={`/payroll/employees/${m.employee_id}?action=rehire`}>Rehire</Link>
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={onClose} className="rounded-sm" data-testid="dup-cancel">Cancel</Button>
            <Button variant="outline" onClick={() => setMatches(null)} className="rounded-sm" data-testid="dup-back">Back to form</Button>
            <Button onClick={() => submit({ force: true })} disabled={busy}
              className="rounded-sm bg-primary text-primary-foreground" data-testid="dup-create-separate">
              {busy ? "Creating…" : "Create separate employee"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg bg-card" data-testid="employee-create-dialog">
        <DialogHeader><DialogTitle>New employee</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2 mt-2">
          <div><Label className="overline">First name *</Label>
            <Input value={f.first_name} onChange={set("first_name")} className="rounded-sm" data-testid="emp-first-name" /></div>
          <div><Label className="overline">Last name *</Label>
            <Input value={f.last_name} onChange={set("last_name")} className="rounded-sm" data-testid="emp-last-name" /></div>
          <div><Label className="overline">Preferred name</Label>
            <Input value={f.preferred_name} onChange={set("preferred_name")} className="rounded-sm" /></div>
          <div><Label className="overline">Job title</Label>
            <Input value={f.job_title} onChange={set("job_title")} className="rounded-sm" data-testid="emp-job-title" /></div>
          <div><Label className="overline">Email</Label>
            <Input type="email" value={f.email} onChange={set("email")} className="rounded-sm" data-testid="emp-email" /></div>
          <div><Label className="overline">Mobile</Label>
            <Input value={f.mobile} onChange={set("mobile")} className="rounded-sm" data-testid="emp-mobile" /></div>
          <div><Label className="overline">Date of birth</Label>
            <Input type="date" value={f.dob} onChange={set("dob")} className="rounded-sm num" data-testid="emp-dob" /></div>
          <div><Label className="overline">Start date *</Label>
            <Input type="date" value={f.employment_start_date} onChange={set("employment_start_date")}
              className="rounded-sm num" data-testid="emp-start-date" /></div>
          <div><Label className="overline">Employment type</Label>
            <Select value={f.employment_type} onValueChange={set("employment_type")}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="emp-type"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">
                {TYPE_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select></div>
          <div><Label className="overline">Status</Label>
            <Select value={f.status} onValueChange={set("status")}>
              <SelectTrigger className="rounded-sm text-xs"><SelectValue /></SelectTrigger>
              <SelectContent className="bg-popover">
                {STATUS_OPTS.slice(0, 3).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={() => submit()} disabled={busy || !f.first_name.trim() || !f.last_name.trim() || !f.employment_start_date}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="emp-create-submit">
            {busy ? "Adding…" : "Add employee"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
