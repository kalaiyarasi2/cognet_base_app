import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Cloud, RefreshCw, Power, Play, FileText, HardDrive,
  CheckCircle2, XCircle, Search, Folder, ChevronRight, User, AlertCircle, Cpu, Info
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
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle
} from "@/components/ui/dialog";

export const Route = createFileRoute("/drive")({ component: DrivePage });

const POC_ENGINES = [
  { id: "AUTO", label: "Auto Router (Default AI Classification)", desc: "Automatic document classification & pipeline routing", mode: "Default" },
  { id: "CONVERTER", label: "Universal File Converter (Single File)", desc: "Process individual files (CSV, Excel, PDF) into structured JSON/XML", mode: "Single File" },
  { id: "INSURANCE", label: "Insurance Loss Runs & ACORD", desc: "Loss history & ACORD policy extraction", mode: "Single File" },
  { id: "WORK_COMP", label: "Workers' Compensation (ACORD 130)", desc: "Workers' Comp forms & rating schedule audit", mode: "Single File" },
  { id: "BANK_STATEMENT", label: "Bank Statement Extractor", desc: "Financial extraction for bank statements & ledger entries", mode: "Single File" },
  { id: "VENDOR_INVOICE", label: "Vendor Invoice Extractor", desc: "General vendor invoice extraction layer", mode: "Single File" },
  { id: "PAYROLL", label: "Payroll Extractor", desc: "Parsing payroll registers and employee earnings", mode: "Single File" },
  { id: "SBC", label: "SBC (Summary of Benefits & Coverage)", desc: "Parity setup & benefit coverage parsing", mode: "Single File" },
  { id: "RE", label: "RE (Resourcing Edge)", desc: "Resourcing Edge payroll processing engine", mode: "Single File" },
  { id: "RENEWAL", label: "Renewal Process (Census & Rate Audit)", desc: "Census roster matching & benefit renewal audit", mode: "Subfolder Batch" },
  { id: "RPVE", label: "RPVE (Rate & Payroll Verification)", desc: "Rate & Payroll verification engine", mode: "Subfolder Batch" },
];

function DrivePage() {
  const [activeMode, setActiveMode] = useState<"local" | "cloud">("cloud");
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [selectedEngine, setSelectedEngine] = useState("AUTO");
  const [maxPages, setMaxPages] = useState(3);
  const [model, setModel] = useState("gpt-4o");
  const [minScore, setMinScore] = useState(7.0);
  const [copyMode, setCopyMode] = useState(true);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);

  // Cloud OAuth States
  const [cloudInputId, setCloudInputId] = useState("");
  const [cloudInputName, setCloudInputName] = useState("");
  const [cloudOutputId, setCloudOutputId] = useState("");
  const [cloudOutputName, setCloudOutputName] = useState("");

  // Folder Picker States
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<"input" | "output" | null>(null);
  const [currentFolderId, setCurrentFolderId] = useState("root");
  const [folderStack, setFolderStack] = useState<{ id: string; name: string }[]>([{ id: "root", name: "Root" }]);
  const [selectedFolderId, setSelectedFolderId] = useState("");
  const [selectedFolderName, setSelectedFolderName] = useState("");

  // Local Folder Picker States
  const [localPickerOpen, setLocalPickerOpen] = useState(false);
  const [localPickerType, setLocalPickerType] = useState<"input" | "output">("input");

  const addLog = useApp((s) => s.addLog);
  const addActivity = useApp((s) => s.addActivity);

  // Local Drive Status Query
  const status = useQuery({
    queryKey: ["drive-status", input],
    queryFn: () => api.driveStatus(input || undefined),
    enabled: activeMode === "local",
    retry: false,
  });

  // Cloud OAuth Setup Query
  const setupStatus = useQuery({
    queryKey: ["google-setup"],
    queryFn: api.googleCheckSetup,
    enabled: true,
    retry: false,
  });

  // Cloud OAuth Profile Query
  const profile = useQuery({
    queryKey: ["google-profile"],
    queryFn: api.googleProfile,
    enabled: true,
    retry: false,
  });

  // Cloud Folders list inside Picker Dialog
  const folders = useQuery({
    queryKey: ["google-folders", currentFolderId],
    queryFn: () => api.googleDriveFolders(currentFolderId),
    enabled: activeMode === "cloud" && pickerOpen,
    retry: false,
  });

  async function runLocal() {
    setRunning(true);
    try {
      const r = await api.driveClassify({
        drive_input_folder: input || undefined,
        drive_output_folder: output || undefined,
        pdf_max_pages: maxPages,
        min_score: minScore,
        llm_model: model,
        copy_mode: copyMode,
        dry_run: dryRun,
      });
      setResult(r);
      addActivity({ kind: "drive", title: "Drive classification done", detail: JSON.stringify(r).slice(0, 80) });
      addLog("INFO", "drive", "Drive classification done", r);
      toast.success("Drive classification complete");
      status.refetch();
    } catch (e: any) {
      toast.error(e.message);
      addLog("ERROR", "drive", e.message);
    } finally {
      setRunning(false);
    }
  }

  async function runCloud() {
    if (!cloudInputId || !cloudOutputId) {
      return toast.error("Please select both input and output folders.");
    }
    setRunning(true);
    try {
      const r = await api.googleDriveClassify({
        drive_input_folder_id: cloudInputId,
        drive_output_folder_id: cloudOutputId,
        pdf_max_pages: maxPages,
        min_score: minScore,
        llm_model: model,
        copy_mode: copyMode,
        dry_run: dryRun,
        poc_engine: selectedEngine,
      });
      setResult(r);
      addActivity({ kind: "drive", title: "Cloud Drive classification done", detail: JSON.stringify(r).slice(0, 80) });
      addLog("INFO", "drive", "Cloud Drive classification done", r);
      toast.success("Cloud Drive classification complete");
    } catch (e: any) {
      toast.error(e.message);
      addLog("ERROR", "drive", e.message);
    } finally {
      setRunning(false);
    }
  }

  const handleLogin = () => {
    window.location.href = `${getBackendUrl()}/google/login?redirect_to_ui=true`;
  };

  const handleLogout = () => {
    window.location.href = `${getBackendUrl()}/google/logout`;
  };

  // Folder Picker Navigation
  const openPicker = (target: "input" | "output") => {
    setPickerTarget(target);
    setCurrentFolderId("root");
    setFolderStack([{ id: "root", name: "Root" }]);
    setSelectedFolderId("");
    setSelectedFolderName("");
    setPickerOpen(true);
  };

  const handleSelectFolder = (id: string, name: string) => {
    setSelectedFolderId(id);
    setSelectedFolderName(name);
  };

  const handleEnterFolder = (id: string, name: string) => {
    setFolderStack((prev) => [...prev, { id, name }]);
    setCurrentFolderId(id);
    setSelectedFolderId("");
    setSelectedFolderName("");
  };

  const handleNavigateStack = (idx: number) => {
    const target = folderStack[idx];
    setFolderStack((prev) => prev.slice(0, idx + 1));
    setCurrentFolderId(target.id);
    setSelectedFolderId("");
    setSelectedFolderName("");
  };

  const handleConfirmFolder = () => {
    if (pickerTarget === "input") {
      setCloudInputId(selectedFolderId);
      setCloudInputName(selectedFolderName);
    } else {
      setCloudOutputId(selectedFolderId);
      setCloudOutputName(selectedFolderName);
    }
    setPickerOpen(false);
  };

  const selectLocalFolder = (type: "input" | "output") => {
    setLocalPickerType(type);
    setLocalPickerOpen(true);
  };

  const handleLocalFolderSelect = (path: string) => {
    if (localPickerType === "input") {
      setInput(path);
    } else {
      setOutput(path);
    }
  };

  const s = status.data;

  return (
    <div className="space-y-4">
      <PageHeader
        icon={Cloud}
        title="Google Drive"
        description="Classify PDFs directly from a Google Drive folder mounted on the backend host or via Google Cloud OAuth."
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => activeMode === "local" ? status.refetch() : profile.refetch()}>
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </Button>
            {activeMode === "cloud" && profile.data?.authenticated && (
              <Button size="sm" variant="destructive" onClick={handleLogout}>
                <Power className="w-3.5 h-3.5" /> Sign Out
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <StatCard
          label="Google Setup"
          value={setupStatus.data?.oauth_configured ? "Configured" : "Missing Config"}
          icon={setupStatus.data?.oauth_configured ? CheckCircle2 : XCircle}
          accent={setupStatus.data?.oauth_configured ? "success" : "destructive"}
        />
        <StatCard
          label="Account Connection"
          value={profile.data?.authenticated ? "Connected" : "Disconnected"}
          icon={profile.data?.authenticated ? CheckCircle2 : XCircle}
          accent={profile.data?.authenticated ? "success" : "muted"}
        />
      </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {!profile.data?.authenticated ? (
              <Panel title="Google Cloud Connection" description="Connect your Google Account using OAuth" className="lg:col-span-2">
                {!setupStatus.data?.oauth_configured && setupStatus.data?.message && (
                  <div className="bg-destructive/10 border border-destructive/25 text-destructive rounded-md p-3 text-[12px] leading-relaxed mb-3 flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-destructive" />
                    <div>
                      <strong>Server Configuration Required:</strong> client_secret.json is missing on the server. Please place it in the project root to enable Google OAuth.
                    </div>
                  </div>
                )}
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <Cloud className="w-12 h-12 text-muted-foreground/40 mb-3" />
                  <div className="text-[13px] font-semibold mb-1">Not signed in to Google Drive Cloud</div>
                  <p className="text-[12px] text-muted-foreground max-w-sm mb-4 leading-relaxed">
                    Authenticate with your Google Account to browse Cloud Drive directories and run classifications directly in the cloud.
                  </p>
                  <Button onClick={handleLogin} disabled={!setupStatus.data?.oauth_configured} className="gap-2">
                    <Power className="w-3.5 h-3.5" /> Sign in with Google
                  </Button>
                </div>
              </Panel>
            ) : (
              <Panel title="Google Cloud Connection" description="Currently signed-in account details">
                <div className="flex flex-col sm:flex-row items-center gap-3 p-3 rounded-lg border border-border bg-muted/20 justify-between">
                  <div className="flex items-center gap-3 min-w-0 w-full sm:w-auto">
                    <div className="w-10 h-10 rounded-full overflow-hidden border border-border bg-background shrink-0 flex items-center justify-center">
                      {profile.data?.picture ? (
                        <img src={profile.data.picture} alt={profile.data.name || "Profile"} className="w-full h-full object-cover" />
                      ) : (
                        <User className="w-5 h-5 text-muted-foreground" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="text-[12.5px] font-semibold truncate text-foreground">{profile.data?.name || "Connected User"}</div>
                      <div className="text-[11px] text-muted-foreground truncate">{profile.data?.email || "Connected via Google"}</div>
                    </div>
                  </div>
                  <div className="flex gap-1.5 shrink-0 w-full sm:w-auto justify-end mt-2 sm:mt-0">
                    <Button size="sm" variant="outline" onClick={handleLogin} className="text-[11px] h-7 px-2.5">
                      Switch Account
                    </Button>
                    <Button size="sm" variant="destructive" onClick={handleLogout} className="text-[11px] h-7 px-2.5">
                      Sign Out
                    </Button>
                  </div>
                </div>
              </Panel>
            )}

            {profile.data?.authenticated && (
              <Panel title="Cloud Drive Folders" description="Configure input/output folders and classification options">
                <div className="space-y-3">
                  <div>
                    <Label className="text-[11.5px]">Input Folder</Label>
                    <div className="flex gap-1.5 mt-1">
                      <Input value={cloudInputName ? `📁 ${cloudInputName} (ID: ${cloudInputId.slice(0, 8)}...)` : ""} readOnly placeholder="Choose Google Drive input folder..." className="h-8 font-mono text-[11.5px] bg-muted/30 cursor-pointer flex-1" onClick={() => openPicker("input")} />
                      <Button size="sm" variant="outline" className="h-8 w-8 p-0" onClick={() => openPicker("input")}>
                        <Search className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                  <div>
                    <Label className="text-[11.5px]">Output Folder</Label>
                    <div className="flex gap-1.5 mt-1">
                      <Input value={cloudOutputName ? `📁 ${cloudOutputName} (ID: ${cloudOutputId.slice(0, 8)}...)` : ""} readOnly placeholder="Choose Google Drive output folder..." className="h-8 font-mono text-[11.5px] bg-muted/30 cursor-pointer flex-1" onClick={() => openPicker("output")} />
                      <Button size="sm" variant="outline" className="h-8 w-8 p-0" onClick={() => openPicker("output")}>
                        <Search className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  <div>
                    <Label className="text-[11.5px] font-semibold flex items-center gap-1.5 mb-1 text-foreground">
                      <Cpu className="w-3.5 h-3.5 text-primary" /> Select POC Processing Engine
                    </Label>
                    <select
                      value={selectedEngine}
                      onChange={(e) => setSelectedEngine(e.target.value)}
                      className="w-full h-8 px-2.5 text-[11.5px] rounded-md border border-input bg-background font-medium focus:outline-none focus:ring-2 focus:ring-primary/40 cursor-pointer"
                    >
                      {POC_ENGINES.map((eng) => (
                        <option key={eng.id} value={eng.id}>
                          {eng.label}
                        </option>
                      ))}
                    </select>

                    {(() => {
                      const activeObj = POC_ENGINES.find((e) => e.id === selectedEngine);
                      if (!activeObj) return null;
                      const isSubfolder = activeObj.mode === "Subfolder Batch";
                      return (
                        <div className={`mt-2 p-2.5 rounded-md border text-[11.5px] flex items-start gap-2 ${
                          isSubfolder
                            ? "bg-purple-500/10 border-purple-500/30 text-purple-700 dark:text-purple-300"
                            : "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-300"
                        }`}>
                          <Info className="w-4 h-4 shrink-0 mt-0.5" />
                          <div>
                            <div className="font-semibold">{activeObj.label}</div>
                            <div className="text-[11px] opacity-90 mt-0.5">{activeObj.desc}</div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <Label className="text-[11.5px]">Max Pages</Label>
                      <Input type="number" min={1} max={20} value={maxPages} onChange={(e) => setMaxPages(Number(e.target.value))} className="h-8 mt-1" />
                    </div>
                    <div>
                      <Label className="text-[11.5px]">LLM Model</Label>
                      <Input value={model} onChange={(e) => setModel(e.target.value)} className="h-8 mt-1" />
                    </div>
                    <div>
                      <Label className="text-[11.5px]">Min Score</Label>
                      <Input type="number" min={0} max={10} step={0.1} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="h-8 mt-1" />
                    </div>
                  </div>
                  <div className="flex gap-6">
                    <div className="flex items-center gap-2"><Switch checked={copyMode} onCheckedChange={setCopyMode} /><Label className="text-[11.5px]">Copy Mode (keep originals)</Label></div>
                    <div className="flex items-center gap-2"><Switch checked={dryRun} onCheckedChange={setDryRun} /><Label className="text-[11.5px]">Dry Run (classify only)</Label></div>
                  </div>
                  <div className="flex justify-end">
                    <Button size="sm" onClick={runCloud} disabled={running || !cloudInputId || !cloudOutputId}>
                      <Play className="w-3.5 h-3.5" /> {running ? "Running…" : "Run on Cloud Drive"}
                    </Button>
                  </div>
                </div>
              </Panel>
            )}
          </div>

      {result && (
        <Panel title="Last Run Result" className="mt-3">
          <pre className="text-[11.5px] font-mono whitespace-pre-wrap bg-muted/40 rounded-md p-3 max-h-72 overflow-auto">{JSON.stringify(result, null, 2)}</pre>
        </Panel>
      )}

      {/* Folder Picker Modal Dialog */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>Select Google Drive Folder</DialogTitle>
            <DialogDescription>
              Choose a folder as the {pickerTarget === "input" ? "input source" : "output destination"}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            {/* Breadcrumbs stack */}
            <div className="flex items-center flex-wrap gap-1 text-[11px] font-mono bg-muted/50 p-2 rounded border border-border">
              {folderStack.map((item, idx) => (
                <span key={item.id} className="flex items-center gap-1">
                  {idx > 0 && <ChevronRight className="w-3 h-3 text-muted-foreground" />}
                  <button
                    onClick={() => handleNavigateStack(idx)}
                    className="hover:underline hover:text-foreground text-muted-foreground font-semibold"
                  >
                    {item.name}
                  </button>
                </span>
              ))}
            </div>

            {/* Folder list container */}
            <div className="border border-border rounded-lg bg-background max-h-60 overflow-y-auto divide-y divide-border min-h-[160px]">
              {folders.isLoading ? (
                <div className="text-[12px] text-muted-foreground text-center py-12">Loading folders...</div>
              ) : folders.isError ? (
                <div className="text-[12px] text-destructive text-center py-12">Failed to load folders.</div>
              ) : !folders.data?.folders || folders.data.folders.length === 0 ? (
                <div className="text-[12px] text-muted-foreground text-center py-12">No folders found inside this directory.</div>
              ) : (
                folders.data.folders.map((folder) => {
                  const isSelected = selectedFolderId === folder.id;
                  return (
                    <button
                      key={folder.id}
                      onClick={() => handleSelectFolder(folder.id, folder.name)}
                      onDoubleClick={() => handleEnterFolder(folder.id, folder.name)}
                      className={cn(
                        "w-full text-left px-3 py-2 text-[12px] hover:bg-muted flex items-center gap-2 transition-colors",
                        isSelected && "bg-primary/10 text-primary font-medium"
                      )}
                    >
                      <Folder className={cn("w-4 h-4 shrink-0 text-muted-foreground", isSelected && "text-primary")} />
                      <span className="truncate">{folder.name}</span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setPickerOpen(false)}>Cancel</Button>
            <Button
              size="sm"
              onClick={handleConfirmFolder}
              disabled={!selectedFolderId}
            >
              Select Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
