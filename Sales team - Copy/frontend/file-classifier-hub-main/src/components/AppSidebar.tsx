import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard, FileText, Tags,
  Workflow, FolderTree, Cloud, BarChart3, Activity, Terminal,
  Settings2, SlidersHorizontal, Info, Shield, ChevronLeft, ChevronRight,
  RefreshCw, Scale, Cpu, FileCheck, HardDrive, Share2, FileSpreadsheet, Building2,
  CreditCard, ReceiptText, Mail
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface NavItem { label: string; to: string; icon: any; moduleCode?: string; }
interface NavGroup { label: string; items: NavItem[]; }

const groups: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard },
      { label: "Master GPU Engine", to: "/drive-gpu", icon: HardDrive, moduleCode: "DRIVE_GPU" },
    ],
  },
  {
    label: "Sales",
    items: [
      { label: "Accord", to: "/drive-gpu?pipeline=WORK_COMP", icon: FileText, moduleCode: "WORK_COMP" },
      { label: "Insurance", to: "/drive-gpu?pipeline=INSURANCE", icon: Shield, moduleCode: "LOSS_RUN" },
    ],
  },
  {
    label: "Payroll",
    items: [
      { label: "Invoice", to: "/drive-gpu?pipeline=INVOICE", icon: ReceiptText, moduleCode: "INVOICE" },
      { label: "Renewal Process", to: "/renewal-process", icon: RefreshCw, moduleCode: "RENEWAL" },
      { label: "RPVE", to: "/rpve", icon: FileCheck, moduleCode: "RPVE" },
      { label: "SBC", to: "/parity-setup", icon: Scale, moduleCode: "SBC" },
      { label: "RE", to: "/resourcing-edge", icon: Cpu, moduleCode: "RE" },
      { label: "Payroll Extractor", to: "/payroll-extractor", icon: FileSpreadsheet, moduleCode: "PAYROLL" },
    ],
  },
  {
    label: "Finance",
    items: [
      { label: "Bank Statement", to: "/drive-gpu?pipeline=BANK_STATEMENT", icon: CreditCard, moduleCode: "BANK_STATEMENT" },
      { label: "Vendor Invoice", to: "/drive-gpu?pipeline=VENDOR_INVOICE", icon: ReceiptText, moduleCode: "VENDOR_INVOICE" },
    ],
  },
  {
    label: "Tools & Core Engines",
    items: [
      { label: "Text Extraction", to: "/extraction", icon: FileText },
      { label: "Classification", to: "/classification", icon: Tags },
      { label: "File Converter", to: "/converter", icon: RefreshCw },
      { label: "File Organiser", to: "/pipeline", icon: Workflow },
    ],
  },
  {
    label: "Integration",
    items: [
      { label: "Google Drive", to: "/drive", icon: Cloud },
      { label: "OneDrive", to: "/onedrive", icon: Cloud },
      { label: "SharePoint", to: "/sharepoint", icon: Share2 },
      { label: "Outlook Agent", to: "/outlook", icon: Mail },
      { label: "Work Flow Designer", to: "/co-pilot", icon: Workflow },
    ],
  },
  {
    label: "Insight",
    items: [
      { label: "System Health", to: "/health", icon: Activity },
      { label: "Logs", to: "/logs", icon: Terminal },
    ],
  },
  {
    label: "System",
    items: [
      { label: "Tenants", to: "/tenants", icon: Building2 },
      { label: "Configuration", to: "/configuration", icon: SlidersHorizontal },
      { label: "User Access", to: "/access", icon: Shield },
      { label: "Settings", to: "/settings", icon: Settings2 },
      { label: "About", to: "/about", icon: Info },
    ],
  },
];

import { useAuth } from "@/lib/store";

export function AppSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { user } = useAuth();
  const rawModules = user?.allowed_modules;

  function isItemAllowed(item: NavItem): boolean {
    if (item.to === "/tenants") return !!user?.can_manage_tenants || user?.role === "ADMIN";
    if (item.to === "/access") return !!user?.can_manage_users || user?.role === "ADMIN" || user?.role === "TENANT_ADMIN";
    if (["/settings", "/about"].includes(item.to)) return true; // Settings & About always available

    let allowedList: string[] = [];
    if (Array.isArray(rawModules)) {
      allowedList = rawModules;
    } else if (typeof rawModules === "string" && rawModules !== "ALL") {
      allowedList = rawModules.split(",").map((s) => s.trim());
    } else if (rawModules === "ALL") {
      return true;
    }

    if (item.to === "/") {
      return allowedList.includes("dashboard") || allowedList.includes("DASHBOARD");
    }

    const moduleKey = (item.moduleCode || item.to.replace(/^\//, "").split("?")[0]).toUpperCase();
    return allowedList.includes(moduleKey);
  }

  return (
    <aside
      className={cn(
        "shrink-0 border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out flex flex-col",
        collapsed ? "w-[60px]" : "w-[230px]"
      )}
    >
      <div className="h-14 flex items-center gap-2 px-3 border-b border-sidebar-border">
        <div className="w-7 h-7 rounded-md bg-primary/10 text-primary grid place-items-center shrink-0">
          <Shield className="w-4 h-4" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="text-[13px] font-semibold leading-tight truncate">File Classifier</div>
            <div className="text-[10px] tracking-widest text-muted-foreground">AGENT</div>
          </div>
        )}
        <button
          onClick={onToggle}
          className="ml-auto p-1 rounded hover:bg-sidebar-accent text-muted-foreground"
          aria-label="Toggle sidebar"
        >
          {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {groups.map((group) => {
          const visibleItems = group.items.filter(isItemAllowed);
          if (visibleItems.length === 0) return null;

          return (
            <div key={group.label} className="px-2 mb-3">
              {!collapsed && (
                <div className="text-[10px] font-semibold tracking-wider text-muted-foreground px-2 py-1.5">
                  {group.label.toUpperCase()}
                </div>
              )}
              <ul className="space-y-0.5">
                {visibleItems.map((item) => {
                  const active = pathname === item.to;
                  const Icon = item.icon;
                  return (
                    <li key={item.to}>
                      <Link
                        to={item.to}
                        className={cn(
                          "flex items-center gap-2.5 px-2 py-1.5 rounded-md text-[13px] transition-colors",
                          active
                            ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                            : "text-sidebar-foreground hover:bg-sidebar-accent/60",
                          collapsed && "justify-center px-0"
                        )}
                        title={collapsed ? item.label : undefined}
                      >
                        <Icon className={cn("w-4 h-4 shrink-0", active && "text-primary")} />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className={cn("border-t border-sidebar-border px-3 py-2 flex items-center justify-between text-[10px] text-muted-foreground", collapsed && "justify-center")}>
        {!collapsed && <span>v1.0.0</span>}
        <span className="px-1.5 py-0.5 rounded bg-success/15 text-success font-semibold tracking-wider">PROD</span>
      </div>
    </aside>
  );
}
