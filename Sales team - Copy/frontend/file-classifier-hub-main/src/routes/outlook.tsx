import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Mail, RefreshCw, Power, Play, FileText, HardDrive,
  CheckCircle2, XCircle, Search, Folder, ChevronRight, User, AlertCircle, Settings, Cpu, Cloud
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, StatCard } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { api, getBackendUrl } from "@/lib/api";
import { useApp } from "@/lib/store";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { FolderPickerModal } from "@/components/FolderPickerModal";

export const Route = createFileRoute("/outlook")({ component: OutlookPage });

const POC_ENGINES = [
  { id: "AUTO", label: "Auto Router (Default AI Classification)", desc: "Automatic document classification & pipeline routing" },
  { id: "BANK_STATEMENT", label: "Bank Statement Extractor", desc: "Financial extraction for bank statements & ledger entries" },
  { id: "INVOICE", label: "Invoice & Billing Extractor", desc: "Customer invoice & billing data extraction" },
  { id: "VENDOR_INVOICE", label: "Vendor Invoice Extractor", desc: "General vendor invoice extraction layer" },
  { id: "INSURANCE", label: "Insurance Loss Runs & ACORD", desc: "Loss history & ACORD policy extraction" },
  { id: "WORK_COMP", label: "Workers' Compensation (ACORD 130)", desc: "Workers' Comp forms & rating schedule audit" },
  { id: "RPVE", label: "RPVE (Rate & Payroll Verification)", desc: "Rate & Payroll verification engine" },
  { id: "SBC", label: "SBC (Summary of Benefits & Coverage)", desc: "Parity setup & benefit coverage parsing" },
  { id: "RE", label: "RE (Resourcing Edge)", desc: "Resourcing Edge payroll processing engine" },
  { id: "RENEWAL", label: "Renewal Process (Census & Rate Audit)", desc: "Census roster matching & benefit renewal audit" },
];

function OutlookPage() {
  const [activeMode, setActiveMode] = useState<"local" | "cloud">("local");
  const [input, setInput] = useState("C:\\Users\\Intern\\OneDrive - Cognet HR Solutions Pvt Ltd\\AI_Agent_Attachments\\uploads");
  const [output, setOutput] = useState("C:\\Users\\Intern\\OneDrive - Cognet HR Solutions Pvt Ltd\\AI_Agent_Attachments\\sorted");
  const [selectedEngine, setSelectedEngine] = useState("AUTO");
  const [maxPages, setMaxPages] = useState(3);
  const [model, setModel] = useState("gpt-4o");
  const [minScore, setMinScore] = useState(7.0);
  const [copyMode, setCopyMode] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  // Local Folder Picker States
  const [localPickerOpen, setLocalPickerOpen] = useState(false);
  const [localPickerType, setLocalPickerType] = useState<"input" | "output">("input");

  const addLog = useApp((s) => s.addLog);
  const addActivity = useApp((s) => s.addActivity);

  // Local Drive Status Query
  const status = useQuery({
    queryKey: ["outlook-status", input],
    queryFn: () => api.driveStatus(input || undefined),
    enabled: activeMode === "local",
    retry: false,
  });

  async function runOutlookAgent() {
    setRunning(true);
    try {
      const r = await api.gpuDriveClassify({
        input_folder: input || undefined,
        output_folder: output || undefined,
        pdf_max_pages: maxPages,
        min_score: minScore,
        llm_model: model,
        copy_mode: copyMode,
        dry_run: dryRun,
      });
      setResult(r);
      addActivity({ kind: "drive", title: "Outlook Agent processing complete", detail: JSON.stringify(r).slice(0, 80) });
      addLog("INFO", "drive", "Outlook Agent processing completed successfully", r);
      toast.success("Outlook Agent execution complete");
      status.refetch();
    } catch (e: any) {
      toast.error(e.message || "Failed to run Outlook Agent");
      addLog("ERROR", "drive", e.message);
    } finally {
      setRunning(false);
    }
  }

  // User Context & Background Automation
  const user = useApp((s) => s.user);
  const userEmail = user?.email || "kalaiyarasig@cognethro.com";

  const automation = useQuery({
    queryKey: ["automation-status", userEmail],
    queryFn: () => api.automationStatus(userEmail),
    refetchInterval: 4000,
  });

  const isAutoRunning = automation.data?.running ?? false;
  const autoPid = automation.data?.pid;
  const activeUsers = automation.data?.active_users || [];

  async function toggleAutomation() {
    try {
      if (isAutoRunning) {
        await api.automationStop(userEmail);
        toast.info(`Isolated background watcher stopped for ${userEmail}`);
      } else {
        await api.automationStart("outlook", userEmail);
        toast.success(`Isolated background watcher started for ${userEmail}`);
      }
      automation.refetch();
    } catch (err: any) {
      toast.error(err.message || "Failed to toggle background automation");
    }
  }

  const isConnected = status.data?.connected ?? true;
  const pdfCount = status.data?.pdf_count ?? 0;
  const pdfFiles = status.data?.pdf_files || [];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          icon={Mail}
          title="Outlook Email Agent"
          description="Classify PDF attachments directly from your Microsoft Outlook Inbox / AI Agent Attachments folder via Azure MSAL."
        />
        <Button
          variant="outline"
          size="sm"
          onClick={() => { status.refetch(); automation.refetch(); }}
          className="self-start sm:self-auto gap-2 text-xs font-semibold"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </Button>
      </div>

      {/* Background Watcher Banner */}
      <div className="p-4 rounded-xl border bg-card/60 backdrop-blur-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shadow-xs">
        <div className="flex items-center gap-3">
          <div className={cn(
            "p-2.5 rounded-lg border",
            isAutoRunning ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600" : "bg-muted border-muted-foreground/20 text-muted-foreground"
          )}>
            <Power className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold">User-Isolated Automation Service</h4>
              <span className={cn(
                "px-2 py-0.5 text-[10px] font-semibold rounded-full border",
                isAutoRunning
                  ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
                  : "bg-muted text-muted-foreground border-border"
              )}>
                {isAutoRunning ? `RUNNING (PID ${autoPid})` : "STOPPED"}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Target User: <code className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">{userEmail}</code>
              {activeUsers.length > 0 && (
                <span className="ml-2 font-medium text-foreground">
                  ({activeUsers.length} total user process{activeUsers.length > 1 ? "es" : ""} active)
                </span>
              )}
            </p>
          </div>
        </div>
        <Button
          variant={isAutoRunning ? "destructive" : "default"}
          size="sm"
          onClick={toggleAutomation}
          className="gap-2 text-xs font-semibold shrink-0"
        >
          <Power className="w-3.5 h-3.5" />
          {isAutoRunning ? "Stop User Watcher" : "Start Isolated Watcher"}
        </Button>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="flex gap-2 p-1 bg-muted/60 rounded-lg w-fit text-xs font-medium">
        <button
          onClick={() => setActiveMode("local")}
          className={cn(
            "px-4 py-2 rounded-md transition-all flex items-center gap-2",
            activeMode === "local"
              ? "bg-background text-foreground shadow-xs font-semibold"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Mail className="w-3.5 h-3.5" />
          Local Mailbox Watcher
        </button>
        <button
          onClick={() => setActiveMode("cloud")}
          className={cn(
            "px-4 py-2 rounded-md transition-all flex items-center gap-2",
            activeMode === "cloud"
              ? "bg-background text-foreground shadow-xs font-semibold"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Cloud className="w-3.5 h-3.5" />
          Azure MSAL OAuth
        </button>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard
          label="Connection"
          value={isConnected ? "Connected" : "Disconnected"}
          icon={isConnected ? CheckCircle2 : XCircle}
          hint="Outlook Attachment Agent"
          accent={isConnected ? "success" : "destructive"}
        />
        <StatCard
          label="PDFs / Attachments Ready"
          value={pdfCount}
          icon={FileText}
          hint="Files queued in attachment folder"
        />
        <StatCard
          label="Outlook Root"
          value="Mounted"
          icon={HardDrive}
          hint={input || "C:\\Users\\Intern\\OneDrive\\AI_Agent_Attachments"}
          accent="primary"
        />
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Form Controls */}
        <Panel title="Outlook Sync Folders" description="Override default attachment paths and POC engine settings">
          <div className="space-y-4">
            {/* Input Folder */}
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold">Input Folder</Label>
              <div className="flex gap-2">
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="C:\Users\...\AI_Agent_Attachments\uploads"
                  className="text-xs font-mono"
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    setLocalPickerType("input");
                    setLocalPickerOpen(true);
                  }}
                  title="Browse local folders"
                >
                  <Search className="w-4 h-4 text-muted-foreground" />
                </Button>
              </div>
            </div>

            {/* Output Folder */}
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold">Output Folder</Label>
              <div className="flex gap-2">
                <Input
                  value={output}
                  onChange={(e) => setOutput(e.target.value)}
                  placeholder="C:\Users\...\AI_Agent_Attachments\sorted"
                  className="text-xs font-mono"
                />
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => {
                    setLocalPickerType("output");
                    setLocalPickerOpen(true);
                  }}
                  title="Browse local folders"
                >
                  <Search className="w-4 h-4 text-muted-foreground" />
                </Button>
              </div>
            </div>

            {/* POC Processing Engine Dropdown */}
            <div className="space-y-1.5 pt-1">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                <Cpu className="w-3.5 h-3.5 text-primary" />
                <Label className="text-xs font-semibold">Select POC Processing Engine</Label>
              </div>
              <select
                value={selectedEngine}
                onChange={(e) => setSelectedEngine(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {POC_ENGINES.map((engine) => (
                  <option key={engine.id} value={engine.id}>
                    {engine.label}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-muted-foreground">
                {POC_ENGINES.find((e) => e.id === selectedEngine)?.desc}
              </p>
            </div>

            {/* Numeric Parameters */}
            <div className="grid grid-cols-3 gap-3 pt-1">
              <div className="space-y-1.5">
                <Label className="text-xs">Max Pages</Label>
                <Input
                  type="number"
                  value={maxPages}
                  onChange={(e) => setMaxPages(Number(e.target.value))}
                  className="text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">LLM Model</Label>
                <Input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="text-xs font-mono"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Min Score</Label>
                <Input
                  type="number"
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="text-xs"
                />
              </div>
            </div>

            {/* Toggles */}
            <div className="flex items-center gap-6 pt-2">
              <div className="flex items-center gap-2">
                <Switch checked={copyMode} onCheckedChange={setCopyMode} id="copy-mode" />
                <Label htmlFor="copy-mode" className="text-xs cursor-pointer font-medium">Copy Mode</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={dryRun} onCheckedChange={setDryRun} id="dry-run" />
                <Label htmlFor="dry-run" className="text-xs cursor-pointer font-medium">Dry Run</Label>
              </div>
            </div>

            {/* Submit Button */}
            <div className="pt-3">
              <Button
                onClick={runOutlookAgent}
                disabled={running}
                className="w-full gap-2 font-semibold text-xs h-10 shadow-sm"
              >
                {running ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                Run on Outlook Agent
              </Button>
            </div>
          </div>
        </Panel>

        {/* Right Column: Files List */}
        <Panel title="Files in Outlook Mailbox / Attachments" description={`${pdfCount} PDFs ready in input queue`}>
          {pdfFiles.length > 0 ? (
            <div className="divide-y border rounded-md overflow-hidden bg-card">
              {pdfFiles.map((file: string, idx: number) => (
                <div key={idx} className="p-3 flex items-center justify-between text-xs hover:bg-muted/30">
                  <div className="flex items-center gap-2 truncate">
                    <FileText className="w-4 h-4 text-primary shrink-0" />
                    <span className="truncate font-medium">{file}</span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 font-mono shrink-0">
                    Ready
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground text-center py-16 flex flex-col items-center gap-2">
              <Mail className="w-8 h-8 opacity-30" />
              <span>No PDFs found in attachment queue.</span>
            </div>
          )}
        </Panel>
      </div>

      {/* Local Folder Picker Modal */}
      <FolderPickerModal
        open={localPickerOpen}
        onClose={() => setLocalPickerOpen(false)}
        initialPath={localPickerType === "input" ? input : output}
        onSelect={(path) => {
          if (localPickerType === "input") setInput(path);
          else setOutput(path);
        }}
      />
    </div>
  );
}
