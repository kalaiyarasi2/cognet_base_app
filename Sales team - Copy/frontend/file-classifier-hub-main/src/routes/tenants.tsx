import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import {
  Building2, Plus, Check, AlertCircle, Shield, Sliders,
  CheckSquare, Square, RefreshCw, Layers, Lock, Unlock, Sparkles, Trash2, Mail
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

export const Route = createFileRoute("/tenants")({
  component: TenantManagementPage,
});


interface TenantRecord {
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
  email?: string;
  active: boolean;
  enabled_modules: string[];
  output_root: string;
  default_confidence_threshold: number;
}

const ALL_MODULES = [
  // Sales Category
  { code: "ACCORD", name: "Accord (Worker Compensation)", desc: "Worker Compensation PDF Processing (Sales)" },
  { code: "LOSS_RUN", name: "Loss Run (Insurance PDF Extractor)", desc: "Insurance Claims & Plan Comparison (Sales)" },
  
  // Payroll Category
  { code: "INVOICE", name: "Invoice Extractor", desc: "Benefit Invoice Processing (Payroll)" },
  { code: "RPVE", name: "RPVE Engine", desc: "Data Retrieval Ingestion Verification (Payroll)" },
  { code: "SBC", name: "SBC Parity Intellect", desc: "Summary of Benefits & Coverage (Payroll)" },
  { code: "RE", name: "Resourcing Edge (RE)", desc: "Employee Roster Rate & Benefits (Payroll)" },
  
  // Finance Category
  { code: "BANK_STATEMENT", name: "Bank Statement Extractor", desc: "Financial Bank Statement Parsing (Finance)" },
  { code: "VENDOR_INVOICE", name: "Vendor Invoice Extractor", desc: "Vendor Invoice Verification (Finance)" },
];

export function TenantManagementPage() {
  const [tenants, setTenants] = useState<TenantRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  // Form state
  const [tenantName, setTenantName] = useState("");
  const [tenantCode, setTenantCode] = useState("");
  const [tenantEmail, setTenantEmail] = useState("");
  const [selectedModules, setSelectedModules] = useState<string[]>(["INVOICE", "SBC"]);
  const [threshold, setThreshold] = useState(0.85);
  const [submitting, setSubmitting] = useState(false);

  const fetchTenants = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/admin/tenants");
      if (res.ok) {
        const data = await res.json();
        if (data.status === "ok" && Array.isArray(data.tenants)) {
          setTenants(data.tenants);
        }
      }
    } catch (err) {
      toast.error("Failed to load tenant list from backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTenants();
  }, [fetchTenants]);

  function toggleModuleSelection(code: string) {
    setSelectedModules((prev) =>
      prev.includes(code) ? prev.filter((m) => m !== code) : [...prev, code]
    );
  }

  async function handleCreateTenant(e: React.FormEvent) {
    e.preventDefault();
    if (!tenantName.trim() || !tenantCode.trim() || !tenantEmail.trim()) {
      toast.error("Please provide Tenant Name, Tenant Code, and Contact Email.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("http://localhost:8000/api/admin/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_code: tenantCode.trim().toUpperCase(),
          tenant_name: tenantName.trim(),
          email: tenantEmail.trim(),
          active: true,
          enabled_modules: selectedModules,
          default_confidence_threshold: threshold,
        }),
      });

      const data = await res.json();
      if (res.ok && data.status === "ok") {
        toast.success(`Tenant '${tenantCode.toUpperCase()}' created and connected to DB successfully!`);
        setShowModal(false);
        setTenantName("");
        setTenantCode("");
        setTenantEmail("");
        setSelectedModules(["INVOICE", "SBC"]);
        fetchTenants();
      } else {
        toast.error(data.detail || "Failed to create tenant.");
      }
    } catch (err: any) {
      toast.error(err.message || "Network error while creating tenant.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggleModule(tenant: TenantRecord, moduleCode: string) {
    const currentEnabled = tenant.enabled_modules || [];
    const newModules = currentEnabled.includes(moduleCode)
      ? currentEnabled.filter((m) => m !== moduleCode)
      : [...currentEnabled, moduleCode];

    try {
      const res = await fetch(`http://localhost:8000/api/admin/tenants/${tenant.tenant_code}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled_modules: newModules }),
      });

      const data = await res.json();
      if (res.ok && data.status === "ok") {
        toast.success(`Updated module access for tenant '${tenant.tenant_code}'`);
        fetchTenants();
      } else {
        toast.error(data.detail || "Failed to update tenant module access.");
      }
    } catch (err: any) {
      toast.error("Failed to update module access.");
    }
  }

  async function handleToggleTenantStatus(tenant: TenantRecord) {
    const newStatus = !tenant.active;
    try {
      const res = await fetch(`http://localhost:8000/api/admin/tenants/${tenant.tenant_code}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: newStatus }),
      });

      const data = await res.json();
      if (res.ok && data.status === "ok") {
        toast.success(`Tenant '${tenant.tenant_code}' status set to ${newStatus ? 'ACTIVE' : 'INACTIVE'}`);
        fetchTenants();
      }
    } catch {
      toast.error("Failed to update tenant status.");
    }
  }

  async function handleDeleteTenant(tenant: TenantRecord) {
    if (!confirm(`Are you sure you want to permanently delete tenant '${tenant.tenant_name}' (${tenant.tenant_code})?`)) {
      return;
    }
    try {
      const res = await fetch(`http://localhost:8000/api/admin/tenants/${tenant.tenant_code}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (res.ok && data.status === "ok") {
        toast.success(`Tenant '${tenant.tenant_code}' deleted successfully.`);
        fetchTenants();
      } else {
        toast.error(data.detail || "Failed to delete tenant.");
      }
    } catch (err: any) {
      toast.error("Network error while deleting tenant.");
    }
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        icon={Building2}
        title="Tenant Administration"
        description="Create, configure, and manage tenant organizations, output isolation, and module permissions."
        actions={
          <Button size="sm" onClick={() => setShowModal(true)}>
            <Plus className="w-4 h-4 mr-1.5" /> Create New Tenant
          </Button>
        }
      />

      {/* Tenant List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {loading ? (
          <div className="col-span-full text-center py-12 text-muted-foreground text-sm flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-primary" /> Loading tenant configurations...
          </div>
        ) : tenants.length === 0 ? (
          <div className="col-span-full text-center py-12 text-muted-foreground text-sm">
            No tenants configured yet. Click "+ Create New Tenant" to add your first tenant.
          </div>
        ) : (
          tenants.map((t) => (
            <div
              key={t.tenant_code}
              className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-4 hover:border-primary/40 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-foreground text-sm">{t.tenant_name}</h3>
                    <span className="font-mono text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-semibold">
                      {t.tenant_code}
                    </span>
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span>Tenant ID: {t.tenant_id}</span>
                    <span>•</span>
                    <span className="flex items-center gap-1 font-mono text-foreground/90">
                      <Mail className="w-3 h-3 text-primary shrink-0" /> {t.email || "N/A"}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handleToggleTenantStatus(t)}
                    className={`px-2 py-0.5 text-[10px] font-semibold rounded-full flex items-center gap-1 transition-colors ${
                      t.active
                        ? "bg-emerald-500/15 text-emerald-500 hover:bg-emerald-500/25"
                        : "bg-red-500/15 text-red-500 hover:bg-red-500/25"
                    }`}
                  >
                    {t.active ? <Check className="w-2.5 h-2.5" /> : <Lock className="w-2.5 h-2.5" />}
                    {t.active ? "Active" : "Inactive"}
                  </button>
                  <button
                    onClick={() => handleDeleteTenant(t)}
                    className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                    title="Delete Tenant"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <div className="border-t border-border/50 pt-3 space-y-2">
                <div className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
                  Module Permissions:
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {ALL_MODULES.map((mod) => {
                    const isEnabled = (t.enabled_modules || []).includes(mod.code);
                    return (
                      <button
                        key={mod.code}
                        onClick={() => handleToggleModule(t, mod.code)}
                        className={`px-2 py-1.5 rounded text-[11px] font-medium text-left border flex items-center justify-between transition-colors ${
                          isEnabled
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                            : "bg-muted/30 border-border text-muted-foreground hover:bg-muted/50"
                        }`}
                      >
                        <span className="font-mono">{mod.code}</span>
                        {isEnabled ? <CheckSquare className="w-3 h-3 text-emerald-500" /> : <Square className="w-3 h-3 text-muted-foreground" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="text-[11px] text-muted-foreground flex justify-between items-center pt-1 border-t border-border/40">
                <span>Confidence Threshold:</span>
                <span className="font-mono font-semibold text-foreground">{(t.default_confidence_threshold || 0.85) * 100}%</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Modal for Creating New Tenant */}
      {showModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-xl shadow-xl max-w-md w-full p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-semibold text-base text-foreground flex items-center gap-2">
                <Building2 className="w-4 h-4 text-primary" /> Create New Tenant
              </h3>
              <button onClick={() => setShowModal(false)} className="text-muted-foreground hover:text-foreground text-sm">
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateTenant} className="space-y-4">
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Tenant Name <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  placeholder="e.g. XYZ Enterprises"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Tenant Code (Unique ID) <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  placeholder="e.g. CLIENT_B"
                  value={tenantCode}
                  onChange={(e) => setTenantCode(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs font-mono shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Tenant Contact Email <span className="text-red-500 font-bold">*</span> (DB Connection)
                </label>
                <input
                  type="email"
                  placeholder="e.g. admin@xyzenterprises.com"
                  value={tenantEmail}
                  onChange={(e) => setTenantEmail(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 text-xs shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-2">Enable System Modules</label>
                <div className="space-y-2">
                  {ALL_MODULES.map((mod) => {
                    const isChecked = selectedModules.includes(mod.code);
                    return (
                      <div
                        key={mod.code}
                        onClick={() => toggleModuleSelection(mod.code)}
                        className={`p-2.5 rounded-lg border text-xs cursor-pointer flex items-center justify-between transition-colors ${
                          isChecked ? "bg-primary/10 border-primary/40 text-foreground" : "bg-muted/20 border-border text-muted-foreground"
                        }`}
                      >
                        <div>
                          <div className="font-semibold font-mono">{mod.code} - {mod.name}</div>
                          <div className="text-[10px] text-muted-foreground">{mod.desc}</div>
                        </div>
                        {isChecked ? <CheckSquare className="w-4 h-4 text-primary shrink-0" /> : <Square className="w-4 h-4 shrink-0" />}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-foreground block mb-1">Default Confidence Threshold: {(threshold * 100).toFixed(0)}%</label>
                <input
                  type="range"
                  min="0.5"
                  max="0.95"
                  step="0.05"
                  value={threshold}
                  onChange={(e) => setThreshold(parseFloat(e.target.value))}
                  className="w-full accent-primary"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button type="button" variant="outline" size="sm" onClick={() => setShowModal(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={submitting}>
                  {submitting ? "Creating..." : "Create Tenant"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
