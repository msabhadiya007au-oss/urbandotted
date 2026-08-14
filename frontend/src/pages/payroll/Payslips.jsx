import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errText, fmtMoney, downloadFile } from "@/lib/api";
import { useApp } from "@/context/AppContext";
import { PageHeader, Section, Loading, Empty, Pill, Disclaimer } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Download, FileText } from "lucide-react";

const c = (cents) => fmtMoney((cents || 0) / 100);
const TONES = { finalised: "positive", voided: "neutral" };

export default function Payslips() {
  const { fy } = useApp();
  const [list, setList] = useState(null);
  const load = async () => {
    try { const { data } = await api.get(`/payroll/payslips?fy=${fy || ""}`); setList(data.items || []); }
    catch (e) { setList([]); toast.error(errText(e)); }
  };
  useEffect(() => { if (fy) load(); }, [fy]); // eslint-disable-line react-hooks/exhaustive-deps

  const dl = async (ref) => {
    try { await downloadFile(`/payroll/payslips/${ref}/download`, `${ref}.pdf`); }
    catch (e) { toast.error(errText(e)); }
  };

  return (
    <div data-testid="payslips-page">
      <PageHeader title="Payslip Register" subtitle={`Immutable payslips · ${fy || ""}`} />
      <Disclaimer>Payslips are frozen at pay-run finalisation. Regenerating the PDF returns the original values. Voided payslips are preserved for audit.</Disclaimer>
      <Section title={`Payslips ${list ? `(${list.length})` : ""}`} testId="payslip-register">
        {list === null ? <Loading /> : list.length === 0 ? (
          <Empty title="No payslips yet" hint="Finalise a pay run to generate immutable payslips." />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader><TableRow className="hover:bg-transparent">
                {["Employee", "Payslip Ref", "Pay Run", "Period", "Payment", "Gross", "PAYG", "Super", "Net", "Status", ""].map((h) =>
                  <TableHead key={h} className="overline">{h}</TableHead>)}
              </TableRow></TableHeader>
              <TableBody>
                {list.map((r) => (
                  <TableRow key={r.payslip_ref} data-testid={`payslip-row-${r.payslip_ref}`}>
                    <TableCell className="text-xs">{r.employee?.first_name} {r.employee?.last_name}</TableCell>
                    <TableCell className="text-xs num font-semibold">
                      <Link to={`/payroll/pay-runs/${r.pay_run_ref}`} className="hover:underline">{r.payslip_ref}</Link>
                    </TableCell>
                    <TableCell className="text-xs num">{r.pay_run_ref}</TableCell>
                    <TableCell className="text-xs num">{r.period_start} → {r.period_end}</TableCell>
                    <TableCell className="text-xs num">{r.payment_date}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.gross_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.payg_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.super_cents)}</TableCell>
                    <TableCell className="text-xs num text-right">{c(r.net_cents)}</TableCell>
                    <TableCell><Pill tone={TONES[r.status] || "neutral"}>{r.status}</Pill></TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          onClick={() => dl(r.payslip_ref)} data-testid={`payslip-dl-${r.payslip_ref}`}>
                          <Download size={11} /> PDF
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 rounded-sm text-[10px] px-2 gap-1"
                          disabled title="Email service not configured">
                          <FileText size={11} /> Email
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
      <p className="text-[11px] text-muted-foreground mt-4">Email service not configured. Download PDF is available.</p>
    </div>
  );
}
