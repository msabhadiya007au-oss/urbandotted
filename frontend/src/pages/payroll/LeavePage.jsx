import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errText } from "@/lib/api";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Check, X as XIcon } from "lucide-react";

const STATUS_TONES = { pending: "warning", approved: "positive", rejected: "neutral", cancelled: "neutral" };

export default function LeavePage() {
  return (
    <div data-testid="payroll-leave-page">
      <PageHeader title="Leave" subtitle="Leave requests, approvals and the leave ledger" />
      <Disclaimer>Leave rules are per-employee. Accruals are posted automatically when a pay run is finalised, using the employee's configured hours per pay period. Casual employees do not accrue unless you configure them explicitly.</Disclaimer>
      <Tabs defaultValue="requests">
        <TabsList className="rounded-sm bg-muted h-9 mt-4">
          <TabsTrigger value="requests" className="rounded-sm text-xs" data-testid="leave-tab-requests">Requests</TabsTrigger>
          <TabsTrigger value="ledger" className="rounded-sm text-xs" data-testid="leave-tab-ledger">Ledger</TabsTrigger>
        </TabsList>
        <TabsContent value="requests" className="mt-4"><Requests /></TabsContent>
        <TabsContent value="ledger" className="mt-4"><Ledger /></TabsContent>
      </Tabs>
    </div>
  );
}

function Requests() {
  const [list, setList] = useState(null);
  const [status, setStatus] = useState("all");
  const [openNew, setOpenNew] = useState(false);

  const load = async () => {
    try {
      const p = new URLSearchParams();
      if (status !== "all") p.set("status", status);
      const { data } = await api.get(`/payroll/leave-requests?${p.toString()}`);
      setList(data.items || []);
    } catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { load(); }, [status]); // eslint-disable-line

  const act = async (id, action) => {
    try {
      await api.post(`/payroll/leave-requests/${id}/action`, { action, note: "" });
      toast.success(`Request ${action}d`);
      load();
    } catch (e) { toast.error(errText(e)); }
  };

  return (
    <Section title={`Leave requests ${list ? `(${list.length})` : ""}`} testId="leave-requests-list"
      right={<Button size="sm" className="rounded-sm bg-primary text-primary-foreground gap-1.5"
        onClick={() => setOpenNew(true)} data-testid="leave-request-new"><Plus size={14} /> New Request</Button>}>
      <div className="px-4 py-3 border-b border-border flex gap-2">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="h-9 w-40 rounded-sm text-xs" data-testid="leave-status-filter"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-popover">
            <SelectItem value="all">All statuses</SelectItem>
            {["pending", "approved", "rejected", "cancelled"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {list === null ? <Loading /> : list.length === 0 ? (
        <Empty title="No leave requests yet" hint="Create a request for an employee to record and approve leave." />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Employee", "Type", "Period", "Hours", "Reason", "Status", ""].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {list.map((r) => (
                <TableRow key={r.request_id} data-testid={`leave-req-${r.request_id}`}>
                  <TableCell className="text-xs">{r.employee_name}</TableCell>
                  <TableCell className="text-xs capitalize">{r.leave_type}</TableCell>
                  <TableCell className="text-xs num">{r.start_date} → {r.end_date}</TableCell>
                  <TableCell className="text-xs num text-right">{r.hours}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.reason || "—"}</TableCell>
                  <TableCell><Pill tone={STATUS_TONES[r.status] || "neutral"}>{r.status}</Pill></TableCell>
                  <TableCell>
                    {r.status === "pending" && (
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1 text-positive border-positive/40"
                          onClick={() => act(r.request_id, "approve")} data-testid={`leave-approve-${r.request_id}`}><Check size={11} /> Approve</Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          onClick={() => act(r.request_id, "reject")} data-testid={`leave-reject-${r.request_id}`}><XIcon size={11} /> Reject</Button>
                      </div>
                    )}
                    {r.status === "approved" && (
                      <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2"
                        onClick={() => act(r.request_id, "cancel")} data-testid={`leave-cancel-${r.request_id}`}>Cancel</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {openNew && <NewRequestDialog onClose={() => setOpenNew(false)} onCreated={() => { setOpenNew(false); load(); }} />}
    </Section>
  );
}

function NewRequestDialog({ onClose, onCreated }) {
  const [emps, setEmps] = useState([]);
  const [f, setF] = useState({ employee_id: "", leave_type: "annual", start_date: "", end_date: "", hours: "0", reason: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/payroll/employees?status=active").then(({ data }) => setEmps(data.items || [])).catch(() => setEmps([]));
  }, []);
  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/payroll/leave-requests", f);
      toast.success("Leave request created");
      onCreated();
    } catch (e) { toast.error(errText(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-md bg-card" data-testid="leave-req-dialog">
        <DialogHeader><DialogTitle>New leave request</DialogTitle></DialogHeader>
        <div className="grid gap-3 mt-2">
          <div><Label className="overline">Employee</Label>
            <Select value={f.employee_id} onValueChange={(v) => setF({ ...f, employee_id: v })}>
              <SelectTrigger className="rounded-sm text-xs" data-testid="leave-req-emp"><SelectValue placeholder="Select…" /></SelectTrigger>
              <SelectContent className="bg-popover">
                {emps.map((e) => <SelectItem key={e.employee_id} value={e.employee_id}>{e.first_name} {e.last_name}</SelectItem>)}
              </SelectContent>
            </Select></div>
          <div><Label className="overline">Leave type</Label>
            <Input value={f.leave_type} onChange={(e) => setF({ ...f, leave_type: e.target.value })} className="rounded-sm" data-testid="leave-req-type" /></div>
          <div className="grid gap-2 grid-cols-2">
            <div><Label className="overline">Start</Label>
              <Input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} className="rounded-sm num" data-testid="leave-req-start" /></div>
            <div><Label className="overline">End</Label>
              <Input type="date" value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} className="rounded-sm num" data-testid="leave-req-end" /></div>
          </div>
          <div><Label className="overline">Hours</Label>
            <Input type="number" step="0.25" value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} className="rounded-sm num" data-testid="leave-req-hours" /></div>
          <div><Label className="overline">Reason</Label>
            <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} className="rounded-sm" /></div>
        </div>
        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose} className="rounded-sm">Cancel</Button>
          <Button onClick={submit} disabled={busy || !f.employee_id || !f.start_date || !f.end_date || parseFloat(f.hours || "0") <= 0}
            className="rounded-sm bg-primary text-primary-foreground" data-testid="leave-req-submit">
            {busy ? "Saving…" : "Create request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Ledger() {
  const [emps, setEmps] = useState([]);
  const [empId, setEmpId] = useState("");
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/payroll/employees").then(({ data }) => {
      const e = data.items || []; setEmps(e); if (!empId && e[0]) setEmpId(e[0].employee_id);
    }).catch(() => setEmps([]));
  }, []); // eslint-disable-line

  useEffect(() => {
    if (!empId) return;
    api.get(`/payroll/employees/${empId}/leave-ledger`).then(({ data }) => setItems(data.items || []))
      .catch((e) => { setItems([]); toast.error(errText(e)); });
  }, [empId]);

  return (
    <Section title="Leave transaction ledger (immutable)" testId="leave-ledger-section">
      <div className="px-4 py-3 border-b border-border flex gap-2 items-center">
        <span className="text-xs text-muted-foreground">Employee</span>
        <Select value={empId} onValueChange={setEmpId}>
          <SelectTrigger className="h-9 w-60 rounded-sm text-xs" data-testid="leave-ledger-emp"><SelectValue placeholder="Select employee…" /></SelectTrigger>
          <SelectContent className="bg-popover">
            {emps.map((e) => <SelectItem key={e.employee_id} value={e.employee_id}>{e.first_name} {e.last_name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      {!empId ? <Empty title="Select an employee to view leave ledger" /> :
       items === null ? <Loading /> :
       items.length === 0 ? <Empty title="No leave transactions yet" hint="Accruals post automatically when a pay run is finalised. Adjustments and approved leave post here." /> : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow className="hover:bg-transparent">
              {["Date", "Type", "Leave type", "Hours", "Source", "Note"].map((h) => <TableHead key={h} className="overline">{h}</TableHead>)}
            </TableRow></TableHeader>
            <TableBody>
              {items.map((r) => (
                <TableRow key={r.txn_id} data-testid={`leave-txn-${r.txn_id}`}>
                  <TableCell className="text-xs num">{r.effective_date}</TableCell>
                  <TableCell className="text-xs capitalize">{r.txn_type}</TableCell>
                  <TableCell className="text-xs capitalize">{r.leave_type}</TableCell>
                  <TableCell className={`text-xs num text-right ${parseFloat(r.hours || "0") < 0 ? "text-negative" : "text-positive"}`}>{r.hours}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.source_ref || r.source}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.note || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Section>
  );
}
