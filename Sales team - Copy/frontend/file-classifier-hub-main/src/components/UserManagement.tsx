import { useState, useEffect } from "react";
import {
  Users, UserPlus, ShieldCheck, UserRound, CheckCircle2, XCircle,
  Loader2, RefreshCw, Building2, Mail, Search, AlertTriangle, Trash2,
} from "lucide-react";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface PermissionRow {
  id: number;
  email: string;
  full_name: string;
  role: "ADMIN" | "USER";
  access_status: "GRANTED" | "REVOKED";
  source: string;
  granted_by: string;
  granted_at: string;
}

interface EmployeeRow {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  department: string;
  title: string;
  status: string;
  access_status: "GRANTED" | "REVOKED" | "NOT_GRANTED";
  app_role: string;
}

export function UserManagement() {
  const { token, user: adminUser } = useAuth();
  const [permissions, setPermissions] = useState<PermissionRow[]>([]);
  const [employees, setEmployees] = useState<EmployeeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchPermissions, setSearchPermissions] = useState("");
  const [searchEmployees, setSearchEmployees] = useState("");

  // Manual invite form
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteName, setInviteName] = useState("");
  const [inviteRole, setInviteRole] = useState<"ADMIN" | "USER">("USER");
  const [inviting, setInviting] = useState(false);

  const tk = token ?? "";

  async function fetchData() {
    if (!tk) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAdminUsers(tk);
      setPermissions(res.permissions ?? []);
      setEmployees(res.employee_directory ?? []);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load user data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchData(); }, [tk]);

  async function handleGrant(email: string, name: string, role: string, source = "EXISTING_DB", allowed_modules = "ALL") {
    setActionLoading(email);
    try {
      await api.grantAccess(tk, { email, full_name: name, role, source, allowed_modules });
      toast.success(`Access granted to ${email}`);
      await fetchData();
    } catch (e: any) {
      toast.error(e?.message ?? "Failed to grant access.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRevoke(email: string) {
    setActionLoading(email);
    try {
      await api.revokeAccess(tk, email);
      toast.success(`Access revoked for ${email}`);
      await fetchData();
    } catch (e: any) {
      toast.error(e?.message ?? "Failed to revoke access.");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDelete(email: string) {
    if (!window.confirm(`Are you sure you want to permanently delete user permission for ${email}?`)) {
      return;
    }
    setActionLoading(email);
    try {
      await api.deleteAccess(tk, email);
      toast.success(`User permission deleted for ${email}`);
      await fetchData();
    } catch (e: any) {
      toast.error(e?.message ?? "Failed to delete user permission.");
    } finally {
      setActionLoading(null);
    }
  }

  // Module permission checkboxes
  const AVAILABLE_MODULES = [
    { id: "CONVERTER", label: "File Converter" },
    { id: "SBC", label: "Parity Setup (SBC)" },
    { id: "RENEWAL", label: "Renewal Process" },
    { id: "RE", label: "Resourcing Edge" },
    { id: "RPVE", label: "RPVE" },
    { id: "PIPELINE", label: "File Organiser" },
    { id: "DRIVE", label: "Google Drive" },
    { id: "ONEDRIVE", label: "OneDrive" },
    { id: "SHAREPOINT", label: "SharePoint Automation" },
    { id: "OUTLOOK", label: "Outlook Agent" },
    { id: "CO-PILOT", label: "Work Flow Designer" },
    { id: "DRIVE_GPU", label: "Master GPU Engine" },
    { id: "WORK_COMP", label: "Accord (Work Comp)" },
    { id: "LOSS_RUN", label: "Insurance (Loss Run)" },
    { id: "INVOICE", label: "Invoice" },
    { id: "PAYROLL", label: "Payroll Extractor" },
    { id: "BANK_STATEMENT", label: "Bank Statement" },
    { id: "VENDOR_INVOICE", label: "Vendor Invoice" },
    { id: "EXTRACTION", label: "Text Extraction" },
    { id: "CLASSIFICATION", label: "Classification" },
    { id: "HEALTH", label: "System Health" },
    { id: "LOGS", label: "Logs" },
    { id: "CONFIGURATION", label: "Configuration" },
  ];

  const [selectedModules, setSelectedModules] = useState<string[]>(["CONVERTER", "SBC"]);

  function toggleModule(modId: string) {
    setSelectedModules((prev) =>
      prev.includes(modId) ? prev.filter((m) => m !== modId) : [...prev, modId]
    );
  }

  async function handleInvite() {
    if (!inviteEmail.trim()) {
      toast.error("Please enter an email address.");
      return;
    }
    setInviting(true);
    try {
      await api.grantAccess(tk, {
        email: inviteEmail.trim().toLowerCase(),
        full_name: inviteName.trim() || undefined,
        role: inviteRole,
        source: "MANUAL",
        allowed_modules: inviteRole === "ADMIN" ? "ALL" : selectedModules,
      });
      toast.success(`${inviteRole} access granted to ${inviteEmail}`);
      setInviteEmail("");
      setInviteName("");
      setInviteRole("USER");
      setSelectedModules(["CONVERTER", "SBC"]);
      await fetchData();
    } catch (e: any) {
      toast.error(e?.message ?? "Failed to grant access.");
    } finally {
      setInviting(false);
    }
  }

  // Filter helpers
  const filteredPerms = permissions.filter(
    (p) =>
      p.email.toLowerCase().includes(searchPermissions.toLowerCase()) ||
      p.full_name.toLowerCase().includes(searchPermissions.toLowerCase())
  );
  const filteredEmps = employees.filter(
    (e) =>
      e.email.toLowerCase().includes(searchEmployees.toLowerCase()) ||
      e.full_name.toLowerCase().includes(searchEmployees.toLowerCase()) ||
      e.department.toLowerCase().includes(searchEmployees.toLowerCase())
  );

  const canInvite = !!adminUser?.can_manage_users;
  const isGlobalAdmin = !!adminUser?.can_manage_tenants;

  const adminModulesRaw = adminUser?.allowed_modules;
  let adminAllowedList: string[] = [];
  if (Array.isArray(adminModulesRaw)) {
    adminAllowedList = adminModulesRaw.map(s => s.toLowerCase());
  } else if (typeof adminModulesRaw === "string" && adminModulesRaw !== "ALL") {
    adminAllowedList = adminModulesRaw.split(",").map(s => s.trim().toLowerCase());
  }
  
  const visibleModules = isGlobalAdmin || adminModulesRaw === "ALL"
    ? AVAILABLE_MODULES
    : AVAILABLE_MODULES.filter(m => adminAllowedList.includes(m.id.toLowerCase()));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Users className="w-5 h-5 text-primary" />
            User Access Management
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Control who can access the platform. Manage granular app permissions and employee access.
          </p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border hover:bg-accent transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2.5 p-3.5 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* ─── Manual Invite ─── */}
      {canInvite && (
        <section className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-[13px] font-semibold mb-4 flex items-center gap-2">
            <UserPlus className="w-4 h-4 text-primary" />
            Grant Access — Manual Invite & App Selection
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Email Address *</label>
              <div className="relative">
                <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  id="invite-email-input"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="user@company.com"
                  className="w-full h-9 pl-8 pr-3 text-[12.5px] rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring/40"
                />
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Full Name</label>
              <input
                id="invite-name-input"
                type="text"
                value={inviteName}
                onChange={(e) => setInviteName(e.target.value)}
                placeholder="Jawa (optional)"
                className="w-full h-9 px-3 text-[12.5px] rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring/40"
              />
            </div>
            <div>
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">Role</label>
              <div className="flex gap-2 h-9">
                <button
                  onClick={() => setInviteRole("USER")}
                  className={`flex-1 text-[11px] font-semibold rounded-lg border transition-all ${inviteRole === "USER" ? "bg-blue-500/10 border-blue-500/30 text-blue-600" : "border-border hover:bg-accent text-muted-foreground"}`}
                >
                  USER
                </button>
                {isGlobalAdmin && (
                  <button
                    onClick={() => setInviteRole("ADMIN")}
                    className={`flex-1 text-[11px] font-semibold rounded-lg border transition-all ${inviteRole === "ADMIN" ? "bg-amber-500/10 border-amber-500/30 text-amber-600" : "border-border hover:bg-accent text-muted-foreground"}`}
                  >
                    ADMIN
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Module Selector Checkboxes (Only if role is USER) */}
          {inviteRole === "USER" && (
            <div className="mt-3 pt-3 border-t border-border">
              <label className="block text-[11.5px] font-semibold text-foreground mb-2">
                Select Allowed Applications / Modules for User:
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                {visibleModules.map((mod) => {
                  const isChecked = selectedModules.includes(mod.id);
                  return (
                    <label
                      key={mod.id}
                      onClick={() => toggleModule(mod.id)}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[12px] font-medium cursor-pointer transition-all ${
                        isChecked
                          ? "bg-primary/10 border-primary/40 text-primary"
                          : "border-border bg-background hover:bg-accent text-muted-foreground"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}}
                        className="rounded accent-primary w-3.5 h-3.5"
                      />
                      <span>{mod.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          <button
            id="grant-access-btn"
            onClick={handleInvite}
            disabled={inviting || !inviteEmail.trim()}
            className="mt-4 flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {inviting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserPlus className="w-3.5 h-3.5" />}
            Grant Access
          </button>
        </section>
      )}

      {/* ─── App Permissions ─── */}
      <section className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
          <h3 className="text-[13px] font-semibold flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-amber-500" />
            App Permissions
            <span className="text-[10px] font-normal text-muted-foreground ml-1">
              ({permissions.length} users)
            </span>
          </h3>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
            <input
              type="text"
              value={searchPermissions}
              onChange={(e) => setSearchPermissions(e.target.value)}
              placeholder="Search users…"
              className="h-7 pl-7 pr-3 text-[11.5px] rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring/40 w-44"
            />
          </div>
        </div>

        {loading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : filteredPerms.length === 0 ? (
          <div className="p-8 text-center text-[12px] text-muted-foreground">No permission records found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">User</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Role</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Allowed Apps</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Status</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Source</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Granted By</th>
                  {canInvite && <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredPerms.map((p: any) => (
                  <tr key={p.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{p.full_name}</div>
                      <div className="text-[10.5px] text-muted-foreground">{p.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      {p.role === "ADMIN" ? (
                        <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 font-semibold uppercase tracking-wider">
                          <ShieldCheck className="w-2.5 h-2.5" /> Admin
                        </span>
                      ) : p.role === "TENANT_ADMIN" ? (
                        <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 font-semibold uppercase tracking-wider">
                          <ShieldCheck className="w-2.5 h-2.5" /> Tenant Admin
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 font-semibold uppercase tracking-wider">
                          <UserRound className="w-2.5 h-2.5" /> User
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 max-w-[200px]">
                      {p.role === "ADMIN" || p.allowed_modules === "ALL" ? (
                        <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
                          All Modules (Full Access)
                        </span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {(typeof p.allowed_modules === "string" ? p.allowed_modules.split(",") : p.allowed_modules || []).map((m: string) => (
                            <span key={m} className="text-[9.5px] px-1.5 py-0.5 rounded bg-accent text-accent-foreground font-medium">
                              {m.trim()}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {p.access_status === "GRANTED" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
                          <CheckCircle2 className="w-3 h-3" /> Granted
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] text-destructive font-medium">
                          <XCircle className="w-3 h-3" /> Revoked
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{p.source}</td>
                    <td className="px-4 py-3 text-muted-foreground">{p.granted_by}</td>
                    {canInvite && (
                      <td className="px-4 py-3 text-right">
                        {actionLoading === p.email ? (
                          <Loader2 className="w-4 h-4 animate-spin ml-auto text-muted-foreground" />
                        ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            {p.access_status === "GRANTED" ? (
                              <button
                                id={`revoke-btn-${p.email.replace(/[@.]/g, "-")}`}
                                onClick={() => handleRevoke(p.email)}
                                className="text-[10px] px-2.5 py-1 rounded-lg border border-amber-500/30 text-amber-600 hover:bg-amber-500/10 transition-colors font-medium"
                              >
                                Revoke
                              </button>
                            ) : (
                              <button
                                id={`restore-btn-${p.email.replace(/[@.]/g, "-")}`}
                                onClick={() => handleGrant(p.email, p.full_name, p.role, p.source, p.allowed_modules)}
                                className="text-[10px] px-2.5 py-1 rounded-lg border border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10 transition-colors font-medium"
                              >
                                Restore
                              </button>
                            )}
                            <button
                              id={`delete-btn-${p.email.replace(/[@.]/g, "-")}`}
                              onClick={() => handleDelete(p.email)}
                              title="Delete user permission record"
                              className="p-1.5 rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ─── Employee Directory ─── */}
      <section className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3">
          <h3 className="text-[13px] font-semibold flex items-center gap-2">
            <Building2 className="w-4 h-4 text-blue-500" />
            Company Employee Directory
            <span className="text-[10px] font-normal text-muted-foreground ml-1">
              ({employees.length} employees)
            </span>
          </h3>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
            <input
              type="text"
              value={searchEmployees}
              onChange={(e) => setSearchEmployees(e.target.value)}
              placeholder="Search directory…"
              className="h-7 pl-7 pr-3 text-[11.5px] rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring/40 w-44"
            />
          </div>
        </div>

        {loading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : filteredEmps.length === 0 ? (
          <div className="p-8 text-center text-[12px] text-muted-foreground">No employees found.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Employee</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Department</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Title</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">App Access</th>
                  {canInvite && <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredEmps.map((e) => (
                  <tr key={e.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{e.full_name}</div>
                      <div className="text-[10.5px] text-muted-foreground">{e.email}</div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{e.department}</td>
                    <td className="px-4 py-3 text-muted-foreground">{e.title}</td>
                    <td className="px-4 py-3">
                      {e.access_status === "GRANTED" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-medium">
                          <CheckCircle2 className="w-3 h-3" />
                          {e.app_role !== "NONE" ? e.app_role : "Granted"}
                        </span>
                      ) : e.access_status === "REVOKED" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-destructive font-medium">
                          <XCircle className="w-3 h-3" /> Revoked
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground">Not Granted</span>
                      )}
                    </td>
                    {canInvite && (
                      <td className="px-4 py-3 text-right">
                        {actionLoading === e.email ? (
                          <Loader2 className="w-4 h-4 animate-spin ml-auto text-muted-foreground" />
                        ) : e.access_status === "GRANTED" ? (
                          <button
                            id={`emp-revoke-btn-${e.email.replace(/[@.]/g, "-")}`}
                            onClick={() => handleRevoke(e.email)}
                            className="text-[10px] px-2.5 py-1 rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 transition-colors font-medium"
                          >
                            Revoke Access
                          </button>
                        ) : (
                          <button
                            id={`emp-grant-btn-${e.email.replace(/[@.]/g, "-")}`}
                            onClick={() => handleGrant(e.email, e.full_name, "USER", "EXISTING_DB")}
                            className="text-[10px] px-2.5 py-1 rounded-lg border border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10 transition-colors font-medium"
                          >
                            Grant Access
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
