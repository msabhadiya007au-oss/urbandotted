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
import { Plus, Search } from "lucide-react";

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

export default function Employees() {
  const [list, setList] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);

  const load = async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (status !== "all") params.set("status", status);
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
        right={
          <Button size="sm" className="rounded-sm bg-primary text-primary-foreground gap-1.5"
            onClick={() => setCreateOpen(true)} data-testid="employee-new-btn">
            <Plus size={14} /> New Employee
          </Button>
        }
      />

      <Section title={`Directory ${list ? `(${list.length})` : ""}`} testId="employees-directory">
        <div className="px-4 py-3 border-b border-border flex gap-2 flex-wrap items-center">
          <div className="relative flex-1 max-w-sm">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, email, title…"
              className="pl-8 h-9 rounded-sm text-sm" data-testid="employee-search" />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="employee-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover">
              <SelectItem value="all">All statuses</SelectItem>
              {STATUS_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {list === null ? <Loading /> : list.length === 0 ? (
          <Empty title="No employees yet" hint="Add your first employee to get started with payroll." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Name", "Job title", "Type", "Status", "Email", "Start"].map((h) =>
                  <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {list.map((e) => (
                  <TableRow key={e.employee_id} data-testid={`employee-row-${e.employee_id}`}>
                    <TableCell className="text-xs font-semibold">
                      <Link to={`/payroll/employees/${e.employee_id}`} className="hover:underline">
                        {e.preferred_name || e.first_name} {e.last_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{e.job_title || "—"}</TableCell>
                    <TableCell className="text-xs capitalize">{(e.employment_type || "").replace("_", " ")}</TableCell>
                    <TableCell><Pill tone={STATUS_TONES[e.status] || "neutral"}>{(e.status || "").replace("_", " ")}</Pill></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{e.email || "—"}</TableCell>
                    <TableCell className="text-xs num">{e.employment_start_date || "—"}</TableCell>
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
    email: "", mobile: "", employment_type: "full_time", status: "active",
    job_title: "", department: "", employment_start_date: "",
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const payload = { ...f };
      if (!payload.email) delete payload.email;
      const { data } = await api.post("/payroll/employees", payload);
      toast.success(`Added ${data.first_name} ${data.last_name}`);
      onCreated();
      navigate(`/payroll/employees/${data.employee_id}`);
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };

  const set = (k) => (v) => setF((p) => ({ ...p, [k]: typeof v === "string" ? v : v.target.value }));

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
            <Input value={f.mobile} onChange={set("mobile")} className="rounded-sm" /></div>
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
                {STATUS_OPTS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select></div>
          <div className="sm:col-span-2"><Label className="overline">Start date</Label>
            <Input type="date" value={f.employment_start_date} onChange={set("employment_start_date")}
              className="rounded-sm num" data-testid="emp-start-date" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !f.first_name.trim() || !f.last_name.trim()}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="emp-create-submit">
            {busy ? "Adding…" : "Add employee"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
