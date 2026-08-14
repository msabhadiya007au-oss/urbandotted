import React from "react";
import { Link } from "react-router-dom";
import { PageHeader, Section, Pill, Disclaimer } from "@/components/shared";
import { Users, Settings as SettingsIcon, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Payroll Dashboard — Phase 1 placeholder.
 * KPI cards, charts, and pay-run widgets arrive in Phase 5. For now this page
 * surfaces the compliance banners the user explicitly asked for and links to
 * the two Phase-1 destinations: Employees and Payroll Settings.
 */
export default function PayrollDashboard() {
  return (
    <div data-testid="payroll-dashboard-page">
      <PageHeader
        title="Payroll"
        subtitle="Australian payroll management for Urban Dotted. Phase 1 — employees and settings."
      />

      <div className="grid gap-2 md:grid-cols-3 mb-6">
        <Pill tone="warning" testId="pill-stp">STP: Not connected</Pill>
        <Pill tone="warning" testId="pill-payg">PAYG: Manual — verify tax tables</Pill>
        <Pill tone="neutral" testId="pill-super">Super: Tracked, not transferred</Pill>
      </div>

      <Section title="Get started" testId="payroll-start-section">
        <div className="grid gap-4 md:grid-cols-2 p-4">
          <div className="border border-border p-5">
            <div className="flex items-start gap-3">
              <SettingsIcon size={18} className="mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-semibold">Configure employer profile</div>
                <div className="text-xs text-muted-foreground mt-1">
                  ABN, address, default pay frequency and super rate. Filled once, reused on every payslip.
                </div>
                <Button asChild size="sm" variant="outline" className="mt-3 rounded-sm text-xs">
                  <Link to="/settings" data-testid="go-payroll-settings">Open Payroll Settings</Link>
                </Button>
              </div>
            </div>
          </div>
          <div className="border border-border p-5">
            <div className="flex items-start gap-3">
              <Users size={18} className="mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-semibold">Add your employees</div>
                <div className="text-xs text-muted-foreground mt-1">
                  Identity, employment, pay basis, super and (optionally) bank details. All encrypted at rest.
                </div>
                <Button asChild size="sm" className="mt-3 rounded-sm text-xs bg-primary text-primary-foreground">
                  <Link to="/payroll/employees" data-testid="go-employees">Open Employees</Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Coming next" testId="payroll-coming">
        <ul className="p-4 text-sm text-muted-foreground list-disc pl-8 space-y-1">
          <li>Phase 2 — Pay Runs (weekly, fortnightly, monthly, fixed) with day-by-day hours entry.</li>
          <li>Phase 3 — Payslip PDF generation with YTD summary and page-2 breakdown.</li>
          <li>Phase 4 — Superannuation tracking, leave ledger, and payroll reports.</li>
          <li>Phase 5 — Accounting integration (P&amp;L, cash flow, accountant export).</li>
        </ul>
      </Section>

      <div className="mt-4">
        <Disclaimer>
          <AlertTriangle size={12} className="inline mr-1 -mt-0.5" /> Payroll is bookkeeping software. It does not lodge STP, remit PAYG, transfer super,
          or assess Fair Work / Award classifications. You remain responsible for legal compliance.
        </Disclaimer>
      </div>
    </div>
  );
}
