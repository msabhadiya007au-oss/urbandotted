import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import "@/App.css";
import { AppProvider, useApp } from "@/context/AppContext";
import AppLayout from "@/components/AppLayout";
import { Loading } from "@/components/shared";
import Login, { AuthCallback } from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Transactions from "@/pages/Transactions";
import Expenses, { CategoryDetail } from "@/pages/Expenses";
import { Sales, Refunds, Advertising } from "@/pages/Revenue";
import { Inventory, Cogs, Assets } from "@/pages/InventoryCogs";
import { Suppliers, SupplierDetail, GstCenter, CashFlow } from "@/pages/SuppliersGst";
import { Reports, ReportView, AccountantExport, Documents, Reminders } from "@/pages/ReportsExport";
import { MonthEnd, SearchResults, ImportCsv } from "@/pages/MonthEndSearch";
import Settings from "@/pages/Settings";
import DailyEntry from "@/pages/DailyEntry";
import PayrollDashboard from "@/pages/payroll/PayrollDashboard";
import Employees from "@/pages/payroll/Employees";
import EmployeeProfile from "@/pages/payroll/EmployeeProfile";
import PayRuns from "@/pages/payroll/PayRuns";
import PayRunDetail from "@/pages/payroll/PayRunDetail";
import Payslips from "@/pages/payroll/Payslips";
import SuperLiabilities from "@/pages/payroll/SuperLiabilities";
import LeavePage from "@/pages/payroll/LeavePage";
import PayrollReports from "@/pages/payroll/PayrollReports";

function Protected({ children }) {
  const { user } = useApp();
  if (user === null) return <Loading label="Checking your session" />;
  if (user === false) return <Navigate to="/" replace />;
  return <AppLayout>{children}</AppLayout>;
}

function Entry() {
  const { user } = useApp();
  if (user === null) return <Loading label="Loading" />;
  if (user) return <Navigate to="/dashboard" replace />;
  return <Login />;
}

function Router() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/" element={<Entry />} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/daily" element={<Protected><DailyEntry /></Protected>} />
      <Route path="/daily-entry" element={<Navigate to="/daily" replace />} />
      <Route path="/sales" element={<Protected><Sales /></Protected>} />
      <Route path="/refunds" element={<Protected><Refunds /></Protected>} />
      <Route path="/expenses" element={<Protected><Expenses /></Protected>} />
      <Route path="/expenses/:categoryId" element={<Protected><CategoryDetail /></Protected>} />
      <Route path="/advertising" element={<Protected><Advertising /></Protected>} />
      <Route path="/inventory" element={<Protected><Inventory /></Protected>} />
      <Route path="/cogs" element={<Protected><Cogs /></Protected>} />
      <Route path="/assets" element={<Protected><Assets /></Protected>} />
      <Route path="/suppliers" element={<Protected><Suppliers /></Protected>} />
      <Route path="/suppliers/:supplierId" element={<Protected><SupplierDetail /></Protected>} />
      <Route path="/gst" element={<Protected><GstCenter /></Protected>} />
      <Route path="/cashflow" element={<Protected><CashFlow /></Protected>} />
      <Route path="/transactions" element={<Protected><Transactions /></Protected>} />
      <Route path="/documents" element={<Protected><Documents /></Protected>} />
      <Route path="/documents/missing" element={<Protected><Documents /></Protected>} />
      <Route path="/reports" element={<Protected><Reports /></Protected>} />
      <Route path="/reports/:reportKey" element={<Protected><ReportView /></Protected>} />
      <Route path="/month-end" element={<Protected><MonthEnd /></Protected>} />
      <Route path="/accountant-export" element={<Protected><AccountantExport /></Protected>} />
      <Route path="/reminders" element={<Protected><Reminders /></Protected>} />
      <Route path="/import" element={<Protected><ImportCsv /></Protected>} />
      <Route path="/search" element={<Protected><SearchResults /></Protected>} />
      <Route path="/settings" element={<Protected><Settings /></Protected>} />
      <Route path="/payroll" element={<Protected><PayrollDashboard /></Protected>} />
      <Route path="/payroll/employees" element={<Protected><Employees /></Protected>} />
      <Route path="/payroll/employees/:employeeId" element={<Protected><EmployeeProfile /></Protected>} />
      <Route path="/payroll/pay-runs" element={<Protected><PayRuns /></Protected>} />
      <Route path="/payroll/pay-runs/:ref" element={<Protected><PayRunDetail /></Protected>} />
      <Route path="/payroll/payslips" element={<Protected><Payslips /></Protected>} />
      <Route path="/payroll/super" element={<Protected><SuperLiabilities /></Protected>} />
      <Route path="/payroll/leave" element={<Protected><LeavePage /></Protected>} />
      <Route path="/payroll/reports" element={<Protected><PayrollReports /></Protected>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Router />
        <Toaster position="bottom-right" duration={2500}
          toastOptions={{ style: { borderRadius: 2, fontFamily: "Manrope" } }} />
      </BrowserRouter>
    </AppProvider>
  );
}
