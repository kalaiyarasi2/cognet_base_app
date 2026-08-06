import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import {
  Globe, Activity, RefreshCw, Loader2, ShieldCheck, XCircle, Search, Laptop, Clock, Users
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, StatCard } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { api, type UserSessionRecord } from "@/lib/api";
import { useAuth } from "@/lib/store";
import { toast } from "sonner";

export const Route = createFileRoute("/login-monitor")({
  component: LoginMonitorPage,
});

export function LoginMonitorPage() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<UserSessionRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);

  async function loadSessions() {
    setLoading(true);
    try {
      const res = await api.getActiveSessions();
      setSessions(res.sessions || []);
    } catch (e: any) {
      toast.error(e?.message || "Failed to load user login sessions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSessions();
    if (!autoRefresh) return;
    const timer = setInterval(loadSessions, 8000);
    return () => clearInterval(timer);
  }, [autoRefresh]);

  async function handleRevoke(id: number) {
    try {
      await api.revokeSession(id);
      toast.success("User session revoked successfully.");
      loadSessions();
    } catch (e: any) {
      toast.error(e?.message || "Failed to revoke session.");
    }
  }

  const activeSessions = sessions.filter((s) => s.status === "ACTIVE");
  const filtered = sessions.filter(
    (s) =>
      !search ||
      s.user_email.toLowerCase().includes(search.toLowerCase()) ||
      (s.user_name && s.user_name.toLowerCase().includes(search.toLowerCase())) ||
      s.ip_address.includes(search)
  );

  const uniqueIPs = new Set(sessions.map((s) => s.ip_address)).size;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Globe}
        title="User Login & Session Monitor"
        description="Real-time audit log of user logins, client IP addresses (Local & Deployed Public IPs), active sessions, and device telemetry."
        actions={
          <>
            <div className="flex items-center gap-2 mr-2">
              <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} id="session-auto-refresh" />
              <Label htmlFor="session-auto-refresh" className="text-[11.5px]">
                Live Auto-Refresh
              </Label>
            </div>
            <Button size="sm" variant="outline" onClick={loadSessions} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard
          label="Active Users Online"
          value={activeSessions.length}
          icon={Activity}
          hint="Currently online sessions"
          accent="success"
        />
        <StatCard
          label="Total Logins Recorded"
          value={sessions.length}
          icon={Users}
          hint="Stored in user_sessions.db"
        />
        <StatCard
          label="Unique IP Addresses"
          value={uniqueIPs}
          icon={Globe}
          hint="Client IP connections"
        />
      </div>

      <Panel
        title="Live User Session Database (user_sessions.db)"
        description="Dedicated database tracking client IPs, browser User-Agent strings, login timestamps, and active status."
        actions={
          <div className="relative">
            <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search user email or IP address..."
              className="h-7 pl-7 text-[12px] w-64"
            />
          </div>
        }
      >
        {loading && sessions.length === 0 ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-[12px] text-muted-foreground">
            No user sessions found matching your search.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">User</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Role</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Client IP Address</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Device / User Agent</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Login Time</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Last Active</th>
                  <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Status</th>
                  {user?.role === "ADMIN" && (
                    <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Action</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((s) => (
                  <tr key={s.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 font-medium">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-primary/10 text-primary font-bold text-xs flex items-center justify-center">
                          {(s.user_name || s.user_email).charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div>{s.user_name || s.user_email}</div>
                          <div className="text-[10.5px] text-muted-foreground font-mono">{s.user_email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 text-[10px] font-semibold rounded ${
                          s.user_role === "ADMIN"
                            ? "bg-amber-500/10 text-amber-600 border border-amber-500/20"
                            : "bg-blue-500/10 text-blue-600 border border-blue-500/20"
                        }`}
                      >
                        {s.user_role}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[11.5px] font-semibold text-primary">
                      {s.ip_address}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground max-w-[220px] truncate" title={s.user_agent || ""}>
                      {s.user_agent || "Unknown Browser"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {s.login_time ? new Date(s.login_time).toLocaleString() : "N/A"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {s.last_active ? new Date(s.last_active).toLocaleString() : "N/A"}
                    </td>
                    <td className="px-4 py-3">
                      {s.status === "ACTIVE" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-semibold bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Active
                        </span>
                      ) : s.status === "REVOKED" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-destructive font-semibold bg-destructive/10 px-2.5 py-0.5 rounded-full border border-destructive/20">
                          <XCircle className="w-3 h-3" /> Revoked
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground">{s.status}</span>
                      )}
                    </td>
                    {user?.role === "ADMIN" && (
                      <td className="px-4 py-3 text-right">
                        {s.status === "ACTIVE" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRevoke(s.id)}
                            className="h-7 text-[10.5px] text-destructive border-destructive/30 hover:bg-destructive/10"
                          >
                            Revoke Session
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
