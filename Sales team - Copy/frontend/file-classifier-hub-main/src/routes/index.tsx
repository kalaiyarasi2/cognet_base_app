import { createFileRoute } from "@tanstack/react-router";
import { useNavigate } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect, useMemo } from "react";
import { toast } from "sonner";
import {
  LayoutDashboard, Files, CheckCircle2, ScanLine, FileText, ScanSearch,
  Tags, XCircle, Layers, Timer, Workflow, Sparkles,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid,
  LineChart, Line, PieChart, Pie, Cell, Legend,
} from "recharts";
import { PageHeader } from "@/components/PageHeader";
import { Panel, StatCard } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { useApp, useAuth } from "@/lib/store";
import { api } from "@/lib/api";

export const Route = createFileRoute("/")({ component: Dashboard });

const CHART_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#6366f1", "#14b8a6"];

function Dashboard() {
  const stats = useApp((s) => s.stats);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  // Guard: if user is not ADMIN, redirect to their first allowed module
  useEffect(() => {
    if (user && user.role !== "ADMIN") {
      const rawModules = user.allowed_modules;
      let allowedList: string[] = [];
      if (Array.isArray(rawModules)) {
        allowedList = rawModules;
      } else if (typeof rawModules === "string" && rawModules !== "ALL") {
        allowedList = rawModules.split(",").map((s) => s.trim().toUpperCase());
      } else if (rawModules === "ALL") {
        // If they have ALL but are not admin, fallback to their first likely module
        allowedList = ["CONVERTER"];
      }

      const getModuleUrl = (moduleCode: string) => {
        const routeMap: Record<string, string> = {
          "INVOICE": "/drive-gpu?pipeline=INVOICE",
          "SBC": "/parity-setup",
          "RPVE": "/rpve",
          "RE": "/resourcing-edge",
          "LOSS_RUN": "/drive-gpu?pipeline=INSURANCE",
          "WORK_COMP": "/drive-gpu?pipeline=WORK_COMP",
          "BANK_STATEMENT": "/drive-gpu?pipeline=BANK_STATEMENT",
          "VENDOR_INVOICE": "/drive-gpu?pipeline=VENDOR_INVOICE",
          "DRIVE_GPU": "/drive-gpu",
          "RENEWAL": "/renewal-process",
          "PIPELINE": "/pipeline",
          "CONVERTER": "/converter",
          "PAYROLL": "/payroll-extractor",
          "PSH_CLAIM": "/psh-claim-validator",
          "EXTRACTION": "/extraction",
          "CLASSIFICATION": "/classification"
        };
        return routeMap[moduleCode] || `/${moduleCode.toLowerCase()}`;
      };

      const validModules = allowedList.filter(m => m !== "DASHBOARD");
      const firstModule = validModules[0];
      if (firstModule) {
        navigate({ to: getModuleUrl(firstModule) as any });
      }
    }
  }, [user]);

  const [selectedProvider, setSelectedProvider] = useState<"outlook" | "gmail">("outlook");

  const { data: config } = useQuery({
    queryKey: ["config"], queryFn: () => api.config(), retry: false, refetchInterval: 30000,
  });

  const { data: health } = useQuery({
    queryKey: ["health"], queryFn: () => api.health(), retry: false, refetchInterval: 30000,
  });

  const { data: autoStatus, isLoading: isAutoStatusLoading } = useQuery({
    queryKey: ["automation-status"],
    queryFn: () => api.automationStatus(),
    refetchInterval: 3000,
  });

  const { data: autoLogs } = useQuery({
    queryKey: ["automation-logs"],
    queryFn: () => api.automationLogs(15),
    refetchInterval: 3000,
    enabled: !!autoStatus?.running,
  });

  const { data: dbStatsResponse } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: api.getDashboardStats,
    refetchInterval: 5000,
  });

  const dbStats = dbStatsResponse?.stats;

  // Sync selected provider if it is running in background
  useEffect(() => {
    if (autoStatus?.running && autoStatus?.active_provider) {
      setSelectedProvider(autoStatus.active_provider as "outlook" | "gmail");
    }
  }, [autoStatus?.running, autoStatus?.active_provider]);

  const startMutation = useMutation({
    mutationFn: api.automationStart,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      toast.success("Background email automation started!");
    },
    onError: (err: any) => {
      if (err.message.includes("outlook_not_connected")) {
        toast.warning("Outlook is not signed in yet. Redirecting to Microsoft sign-in page...");
        setTimeout(() => navigate({ to: "/onedrive" }), 1500);
      } else if (err.message.includes("gmail_not_connected")) {
        toast.warning("Gmail is not signed in yet. Redirecting to Google sign-in page...");
        setTimeout(() => navigate({ to: "/drive" }), 1500);
      } else {
        toast.error("Failed to start: " + err.message);
      }
    }
  });

  const stopMutation = useMutation({
    mutationFn: api.automationStop,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation-status"] });
      toast.success("Background email automation stopped.");
    },
    onError: (err: any) => {
      toast.error("Failed to stop: " + err.message);
    }
  });

  const handleStart = () => {
    if (!autoStatus) return; // Wait until status is loaded

    const connected = selectedProvider === "outlook" ? autoStatus.outlook_connected : autoStatus.gmail_connected;
    if (!connected) {
      toast.warning(`Please sign in to your ${selectedProvider === "outlook" ? "Microsoft" : "Google"} account first.`);
      navigate({ to: selectedProvider === "outlook" ? "/onedrive" : "/drive" });
      return;
    }
    startMutation.mutate(selectedProvider);
  };

  const totalFiles = dbStats?.totalFiles ?? stats.totalFiles;
  const processed = dbStats?.processed ?? stats.processed;
  const scanned = dbStats?.scanned ?? stats.scanned;
  const digital = dbStats?.digital ?? stats.digital;
  const ocrProcessed = dbStats?.ocrProcessed ?? stats.ocrProcessed;
  const classificationSuccess = dbStats?.classificationSuccess ?? stats.classificationSuccess;
  const failures = dbStats?.failures ?? stats.failures;
  const pipelineRuns = dbStats?.pipelineRuns ?? stats.pipelineRuns;
  const avgMs = dbStats?.avgProcessingMs || (stats.processed ? Math.round(stats.totalProcessingMs / stats.processed) : 0);

  const catData = useMemo(() => {
    const result: { name: string; value: number }[] = [];
    const dbCategories = dbStats?.categoriesFound || stats.categoriesFound;
    
    const keys = Object.keys(dbCategories);
    if (keys.length > 0) {
      for (const k of keys) {
        result.push({ name: k, value: dbCategories[k] });
      }
    } else {
      const fallback = ["PARITY_SETUP", "RENEWAL_PROCESS", "RESOURCING_EDGE", "RPVE", "CONVERTER"];
      for (const f of fallback) {
        result.push({ name: f, value: 1 });
      }
    }
    return result;
  }, [dbStats?.categoriesFound, stats.categoriesFound]);

  const dailyData = (dbStats?.daily && dbStats.daily.length > 0)
    ? dbStats.daily
    : (stats.daily.length ? stats.daily : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => ({ day: d, processed: 0, failed: 0 })));

  const confBuckets = dbStats?.confidenceBuckets || stats.confidenceBuckets;
  const confData = ["0-2", "2-4", "4-6", "6-7", "7-8", "8-9", "9-10"].map((b, i) => ({
    bucket: b, count: confBuckets[i] || 0,
  }));

  return (
    <>
      <PageHeader
        icon={LayoutDashboard}
        title="Dashboard"
        description="Overview of document classification activity, pipeline performance and system health."
        actions={
          <Button size="sm" onClick={() => navigate({ to: "/classification" })}>
            <Sparkles className="w-3.5 h-3.5" /> New Classification
          </Button>
        }
      />

      <Panel title="Continuous Email Automation" description="Monitor and control unread email classification and extraction." className="mb-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Email Provider</span>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value as "outlook" | "gmail")}
                disabled={autoStatus?.running}
                className="h-8 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="outlook">Outlook (Microsoft)</option>
                <option value="gmail">Gmail (Google)</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Connection Status</span>
              {selectedProvider === "outlook" ? (
                autoStatus?.outlook_connected ? (
                  <span className="inline-flex items-center gap-1.5 text-xs text-success bg-success/10 px-2.5 py-1 rounded-md font-semibold border border-success/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-success"></span> Connected
                  </span>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-xs text-warning bg-warning/10 px-2.5 py-1 rounded-md font-semibold border border-warning/20">
                      <span className="w-1.5 h-1.5 rounded-full bg-warning"></span> Requires Sign-in
                    </span>
                    <Button size="sm" variant="outline" className="h-7 text-xs px-2 py-0.5" onClick={() => navigate({ to: "/onedrive" })}>Sign In</Button>
                  </div>
                )
              ) : (
                autoStatus?.gmail_connected ? (
                  <span className="inline-flex items-center gap-1.5 text-xs text-success bg-success/10 px-2.5 py-1 rounded-md font-semibold border border-success/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-success"></span> Connected
                  </span>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-xs text-warning bg-warning/10 px-2.5 py-1 rounded-md font-semibold border border-warning/20">
                      <span className="w-1.5 h-1.5 rounded-full bg-warning"></span> Requires Sign-in
                    </span>
                    <Button size="sm" variant="outline" className="h-7 text-xs px-2 py-0.5" onClick={() => navigate({ to: "/drive" })}>Sign In</Button>
                  </div>
                )
              )}
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">Automation Pipeline</span>
              {autoStatus?.running ? (
                <span className="inline-flex items-center gap-1.5 text-xs text-primary bg-primary/10 px-2.5 py-1 rounded-md font-semibold border border-primary/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-ping"></span> Polling Provider ({autoStatus.active_provider})
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-2.5 py-1 rounded-md font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/45"></span> Idle / Stopped
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 self-end md:self-center">
            {autoStatus?.running ? (
              <Button size="sm" variant="destructive" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending || isAutoStatusLoading}>
                Stop Polling
              </Button>
            ) : (
              <Button size="sm" className="bg-success hover:bg-success/90 text-success-foreground" onClick={handleStart} disabled={startMutation.isPending || isAutoStatusLoading}>
                Start Polling
              </Button>
            )}
          </div>
        </div>

        {autoStatus?.running && autoLogs && autoLogs.logs && autoLogs.logs.length > 0 && (
          <div className="mt-4 pt-3 border-t">
            <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase block mb-1.5">Live Execution Logs</span>
            <pre className="text-[10.5px] font-mono whitespace-pre-wrap bg-muted/45 rounded-md p-2.5 max-h-32 overflow-y-auto leading-relaxed border border-border">
              {autoLogs.logs.join("\n")}
            </pre>
          </div>
        )}
      </Panel>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        <StatCard label="Total Files" value={totalFiles} icon={Files} hint="Logged in database" />
        <StatCard label="Processed" value={processed} icon={CheckCircle2} accent="success" />
        <StatCard label="Scanned PDFs" value={scanned} icon={ScanLine} accent="warning" />
        <StatCard label="Digital PDFs" value={digital} icon={FileText} />
        <StatCard label="OCR Processed" value={ocrProcessed} icon={ScanSearch} accent="muted" />
        <StatCard label="Classification Success" value={classificationSuccess} icon={Tags} accent="success" />
        <StatCard label="Failures" value={failures} icon={XCircle} accent="destructive" />
        <StatCard label="Categories Found" value={catData.length} icon={Layers} />
        <StatCard label="Avg Processing" value={avgMs ? `${avgMs} ms` : "—"} icon={Timer} accent="muted" />
        <StatCard label="Pipeline" value={pipelineRuns || "—"} icon={Workflow} accent={health?.status === "ok" ? "success" : "muted"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Panel title="Category Distribution" description="Share of classified documents by category">
          {catData.length === 0 ? (
            <div className="h-56 grid place-items-center text-[12.5px] text-muted-foreground">No data yet.</div>
          ) : (
            <div className="h-56">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={catData} dataKey="value" nameKey="name" outerRadius={70} innerRadius={40} paddingAngle={2}>
                    {catData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Panel>

        <Panel title="Daily Processing" description="Last 7 days · processed vs failed">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={dailyData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="day" fontSize={10} tickFormatter={(v: string) => v.length > 3 ? v.slice(5) : v} />
                <YAxis fontSize={10} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                <Bar dataKey="processed" fill="hsl(217 91% 60%)" radius={[2, 2, 0, 0]} />
                <Bar dataKey="failed" fill="hsl(0 84% 60%)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Confidence Distribution" description="LLM score buckets across runs">
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={confData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis dataKey="bucket" fontSize={10} />
                <YAxis fontSize={10} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                <Line type="monotone" dataKey="count" stroke="hsl(217 91% 60%)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
    </>
  );
}
