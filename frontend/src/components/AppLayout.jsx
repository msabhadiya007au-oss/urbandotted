import React, { useState, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, TrendingUp, RotateCcw, Receipt, Megaphone, Boxes, Calculator,
  Wrench, Building2, Percent, Waves, ListOrdered, FolderOpen, FileBarChart2,
  CalendarCheck2, FileOutput, BellRing, Settings as SettingsIcon, Plus, Search,
  LogOut, Menu, X, Upload, CalendarDays, Users, ClipboardList, FileText,
  PiggyBank, CalendarClock,
} from "lucide-react";
import { useApp } from "@/context/AppContext";
import { api, fyLabel } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import QuickAdd from "@/components/QuickAdd";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/daily", label: "Daily Entry", icon: CalendarDays },
  { to: "/sales", label: "Sales", icon: TrendingUp },
  { to: "/refunds", label: "Refunds", icon: RotateCcw },
  { to: "/expenses", label: "Expenses", icon: Receipt },
  { to: "/advertising", label: "Advertising", icon: Megaphone },
  { to: "/inventory", label: "Inventory", icon: Boxes },
  { to: "/cogs", label: "COGS", icon: Calculator },
  { to: "/assets", label: "Assets", icon: Wrench },
  { to: "/suppliers", label: "Suppliers", icon: Building2 },
  { to: "/gst", label: "GST", icon: Percent },
  { to: "/cashflow", label: "Cash Flow", icon: Waves },
  { to: "/transactions", label: "Transactions", icon: ListOrdered },
  { to: "/documents", label: "Documents", icon: FolderOpen },
  { to: "/reports", label: "Reports", icon: FileBarChart2 },
  { to: "/month-end", label: "Month-End", icon: CalendarCheck2 },
  { to: "/accountant-export", label: "Accountant Export", icon: FileOutput },
  { to: "/reminders", label: "Reminders", icon: BellRing },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

// Payroll module (Phase 1 exposes Employees + Payroll Settings; further pages
// unlock in later phases). Kept as a separate section so the existing NAV
// order is untouched.
const PAYROLL_NAV = [
  { to: "/payroll", label: "Payroll Dashboard", icon: LayoutDashboard },
  { to: "/payroll/employees", label: "Employees", icon: Users },
  { to: "/payroll/pay-runs", label: "Pay Runs", icon: ClipboardList },
  { to: "/payroll/payslips", label: "Payslips", icon: FileText },
  { to: "/payroll/super", label: "Super", icon: PiggyBank },
  { to: "/payroll/leave", label: "Leave", icon: CalendarClock },
  { to: "/payroll/liabilities", label: "Liabilities", icon: BellRing },
  { to: "/payroll/reports", label: "Payroll Reports", icon: FileBarChart2 },
];

export default function AppLayout({ children }) {
  const { user, meta, fy, setFy, logout } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [quickAdd, setQuickAdd] = useState(null);
  const [query, setQuery] = useState("");
  const [reminderCount, setReminderCount] = useState(0);
  const searchRef = useRef(null);

  useEffect(() => setOpen(false), [location.pathname]);

  useEffect(() => {
    if (!fy) return;
    api.get(`/reminders?fy=${fy}&status=open`)
      .then(({ data }) => setReminderCount(data.items?.length || 0))
      .catch(() => {});
  }, [fy, location.pathname]);

  const submitSearch = (e) => {
    e.preventDefault();
    if (query.trim()) navigate(`/search?q=${encodeURIComponent(query.trim())}`);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar */}
      <aside data-testid="sidebar"
        className={`fixed z-40 inset-y-0 left-0 w-[260px] bg-card border-r border-border flex flex-col
          transition-transform duration-200 ease-out lg:translate-x-0
          ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="px-5 py-5 border-b border-border">
          <Link to="/dashboard" className="block" data-testid="brand-link">
            <div className="font-serif text-[22px] leading-none font-semibold text-primary">
              urban<span className="italic">dotted</span>
            </div>
            <div className="overline mt-1.5">Expense Book</div>
          </Link>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to || location.pathname.startsWith(`${to}/`);
            return (
              <Link key={to} to={to} data-testid={`nav-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
                className={`flex items-center gap-2.5 px-5 py-[9px] text-[13px] border-l-2 transition-colors duration-150
                  ${active ? "border-primary bg-accent/60 text-foreground font-semibold"
                          : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/30"}`}>
                <Icon size={15} strokeWidth={active ? 2.2 : 1.7} />
                <span className="flex-1">{label}</span>
                {label === "Reminders" && reminderCount > 0 && (
                  <span className="num text-[10px] px-1.5 py-0.5 bg-warning/10 text-warning border border-warning/30 rounded-sm"
                    data-testid="nav-reminder-count">{reminderCount}</span>
                )}
              </Link>
            );
          })}

          <div className="mt-4 px-5 pb-1 overline" data-testid="payroll-section-heading">Payroll</div>
          {PAYROLL_NAV.map(({ to, label, icon: Icon }) => {
            const active = location.pathname === to
              || (to !== "/payroll" && location.pathname.startsWith(`${to}/`))
              || (to === "/payroll" && location.pathname === "/payroll");
            return (
              <Link key={to} to={to} data-testid={`nav-${label.toLowerCase().replace(/[^a-z]+/g, "-")}`}
                className={`flex items-center gap-2.5 px-5 py-[9px] text-[13px] border-l-2 transition-colors duration-150
                  ${active ? "border-primary bg-accent/60 text-foreground font-semibold"
                          : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/30"}`}>
                <Icon size={15} strokeWidth={active ? 2.2 : 1.7} />
                <span className="flex-1">{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="px-5 py-3 border-t border-border">
          <div className="text-[11px] text-muted-foreground truncate" data-testid="sidebar-user-email">{user?.email}</div>
          <button onClick={logout} data-testid="logout-btn"
            className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-negative transition-colors">
            <LogOut size={12} /> Sign out
          </button>
        </div>
      </aside>

      {open && <div className="fixed inset-0 z-30 bg-foreground/20 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="lg:pl-[260px]">
        <header className="sticky top-0 z-20 bg-card border-b border-border" data-testid="topbar">
          <div className="flex items-center gap-2 px-4 lg:px-8 h-[60px]">
            <button className="lg:hidden p-2 -ml-2" onClick={() => setOpen((v) => !v)} data-testid="menu-toggle">
              {open ? <X size={18} /> : <Menu size={18} />}
            </button>

            <form onSubmit={submitSearch} className="flex-1 max-w-md relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input ref={searchRef} value={query} onChange={(e) => setQuery(e.target.value)}
                data-testid="global-search-input" placeholder="Search transactions, suppliers, $120, January 2026…"
                className="pl-9 h-9 text-sm rounded-sm bg-background" />
            </form>

            <div className="ml-auto flex items-center gap-2">
              <Select value={fy} onValueChange={setFy}>
                <SelectTrigger className="h-9 w-[150px] rounded-sm text-xs num" data-testid="fy-selector">
                  <SelectValue placeholder="Financial year" />
                </SelectTrigger>
                <SelectContent className="bg-popover">
                  {(meta?.fy_options || []).map((f) => (
                    <SelectItem key={f} value={f} className="num text-xs" data-testid={`fy-option-${f}`}>
                      {fyLabel(f)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button data-testid="quick-add-btn" size="sm"
                    className="h-9 rounded-sm bg-primary text-primary-foreground hover:bg-primary/90 gap-1.5">
                    <Plus size={15} /> <span className="hidden sm:inline">Add</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-popover w-52">
                  <DropdownMenuLabel className="overline">Quick add</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => setQuickAdd("expense")} data-testid="quick-add-expense">Add Expense</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setQuickAdd("sale")} data-testid="quick-add-sale">Add Sale</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setQuickAdd("refund")} data-testid="quick-add-refund">Add Refund</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setQuickAdd("inventory")} data-testid="quick-add-inventory">Add Inventory Purchase</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setQuickAdd("asset")} data-testid="quick-add-asset">Add Asset</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setQuickAdd("receipt")} data-testid="quick-add-receipt">
                    <Upload size={13} className="mr-2" /> Upload Receipt
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main className="px-4 lg:px-8 py-8 max-w-[1600px]">{children}</main>

        <footer className="px-4 lg:px-8 py-6 border-t border-border mt-8">
          <p className="text-[11px] text-muted-foreground max-w-3xl">
            Urban Dotted Expense Book is bookkeeping and management software. Figures shown — including
            GST and BAS summaries — are estimates prepared for review by your accountant or registered
            tax agent. Nothing here is lodged with the ATO, and the app does not determine tax
            deductibility or depreciation treatment. Currency AUD · Timezone Australia/Adelaide.
          </p>
        </footer>
      </div>

      {quickAdd && <QuickAdd type={quickAdd} onClose={() => setQuickAdd(null)} />}
    </div>
  );
}
