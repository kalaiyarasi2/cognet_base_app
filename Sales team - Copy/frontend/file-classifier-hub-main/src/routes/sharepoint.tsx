import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Share2, Play, Square, RefreshCw, FolderInput, FolderOutput,
  Cpu, CheckCircle2, AlertTriangle, FileText, Loader2, HardDrive, Server,
  FolderTree, Files, Info, Terminal, Search, Folder, ChevronRight
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/store";

export const Route = createFileRoute("/sharepoint")({
  component: SharePointAutomationPage,
});

const ENGINE_GROUPS = [
  {
    groupLabel: "📄 Single-File POC Engines",
    engines: [
      { id: "converter", name: "Universal File Converter", desc: "Process individual files (CSV, Excel, PDF) into structured JSON/XML", mode: "Single File" },
      { id: "parity-setup", name: "SBC / Parity Setup", desc: "Extract matrix & copays from individual SBC PDFs", mode: "Single File" },
      { id: "resourcing-edge", name: "Resourcing Edge", desc: "Medical, dental & vision plan rates comparison for single files", mode: "Single File" },
      { id: "drive-gpu", name: "GPU Drive / Classifier", desc: "High-speed OCR & document routing for single files", mode: "Single File" },
    ],
  },
  {
    groupLabel: "📁 Multi-File Batch (Subfolder) POC Engines",
    engines: [
      { id: "renewal-process", name: "Renewal Process (Subfolder Batch)", desc: "Processes client subfolders containing Census + Invoice + Rate files together", mode: "Subfolder Batch" },
      { id: "rpve", name: "RPVE Engine (Subfolder Batch)", desc: "Processes flow subfolders containing template & claims files together", mode: "Subfolder Batch" },
    ],
  },
];

function SharePointAutomationPage() {
  const queryClient = useQueryClient();

  const [inputFolder, setInputFolder] = useState("Clients/Active/PEO Velocity/Sales Support (PEO Velocity)/Invoice To Census Automation");
  const [outputFolder, setOutputFolder] = useState("Clients/Active/PEO Velocity/Sales Support (PEO Velocity)/Invoice To Census Automation/Processed_Outputs");
  const [selectedEngine, setSelectedEngine] = useState("converter");

  // Folder Picker Navigation State
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerTarget, setPickerTarget] = useState<"input" | "output">("input");
  const [currentPath, setCurrentPath] = useState("");
  const [currentFolderId, setCurrentFolderId] = useState<string | undefined>(undefined);
  const [folderStack, setFolderStack] = useState<{ path: string; name: string; id?: string }[]>([
    { path: "", name: "Root" },
  ]);
  const [selectedPath, setSelectedPath] = useState("");

  // SharePoint folder listing query for the visual picker modal
  const foldersQuery = useQuery({
    queryKey: ["sharepoint-browse-folders", currentPath, currentFolderId],
    queryFn: () => api.getSharePointFolders(currentPath, currentFolderId),
    enabled: pickerOpen,
  });

  // Auto-sync folderStack with real Item IDs resolved by backend parentReference chain
  useEffect(() => {
    if (foldersQuery.data?.breadcrumbs && foldersQuery.data.breadcrumbs.length > 0) {
      setFolderStack(foldersQuery.data.breadcrumbs);
    }
  }, [foldersQuery.data?.breadcrumbs]);

  const openPicker = (target: "input" | "output") => {
    setPickerTarget(target);
    const rawPath = target === "input" ? inputFolder : outputFolder;
    const startPath = rawPath ? rawPath.trim() : "";

    if (startPath) {
      const parts = startPath.split("/").filter(Boolean);
      const stack: { path: string; name: string; id?: string }[] = [{ path: "", name: "Root" }];
      let current = "";
      for (const p of parts) {
        current = current ? `${current}/${p}` : p;
        stack.push({ path: current, name: p });
      }
      setFolderStack(stack);
      setCurrentPath(startPath);
      setCurrentFolderId(undefined);
      setSelectedPath(startPath);
    } else {
      setFolderStack([{ path: "", name: "Root" }]);
      setCurrentPath("");
      setCurrentFolderId(undefined);
      setSelectedPath("");
    }
    setPickerOpen(true);
  };

  const handleSelectFolder = (path: string) => {
    setSelectedPath(path);
  };

  const handleEnterFolder = (path: string, name: string, id?: string) => {
    setFolderStack((prev) => [...prev, { path, name, id }]);
    setCurrentPath(path);
    setCurrentFolderId(id);
    setSelectedPath("");
  };

  const handleNavigateStack = (idx: number) => {
    const target = folderStack[idx];
    setFolderStack((prev) => prev.slice(0, idx + 1));
    setCurrentPath(target.path);
    // For Root (idx === 0, empty path) — do NOT pass a folder_id.
    // The drive-root item ID causes the backend to return 0 items and
    // short-circuit before the reliable root-listing fallback runs.
    setCurrentFolderId(idx === 0 ? undefined : target.id);
    setSelectedPath("");
  };

  const handleConfirmFolder = () => {
    const pathToUse = selectedPath || currentPath;
    if (pickerTarget === "input") {
      setInputFolder(pathToUse);
    } else {
      setOutputFolder(pathToUse);
    }
    setPickerOpen(false);
  };

  // Status query
  const { data: statusData, isLoading, refetch } = useQuery({
    queryKey: ["sharepoint-status"],
    queryFn: () => api.getSharePointStatus(),
    refetchInterval: 3000,
  });

  const agent = statusData?.agent;
  const isRunning = agent?.running ?? false;
  const isMultiFile = agent?.is_multi_file ?? ["renewal-process", "rpve"].includes(selectedEngine);
  const history = agent?.history ?? [];
  const logs = agent?.logs ?? [];

  // All engines flat list for lookup
  const allEngines = ENGINE_GROUPS.flatMap((g) => g.engines);
  const currentEngineObj = allEngines.find((e) => e.id === selectedEngine);

  const { user } = useAuth();

  // Start mutation
  const startMutation = useMutation({
    mutationFn: () =>
      api.startSharePointAutomation({
        input_folder: inputFolder,
        output_folder: outputFolder,
        poc_engine: selectedEngine,
        processed_by: user?.email || "SYSTEM",
      }),
    onSuccess: () => {
      toast.success("SharePoint Automation Started!");
      queryClient.invalidateQueries({ queryKey: ["sharepoint-status"] });
    },
    onError: (e: any) => {
      toast.error(e.message || "Failed to start automation");
    },
  });

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: () => api.stopSharePointAutomation(),
    onSuccess: () => {
      toast.info("SharePoint Automation Stopped.");
      queryClient.invalidateQueries({ queryKey: ["sharepoint-status"] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="SharePoint Automation"
        description="Automated document ingestion, processing, and output sync with Microsoft SharePoint."
        icon={Share2}
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        }
      />

      {/* Connection Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl border border-border bg-card shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 text-blue-600 grid place-items-center shrink-0">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold">cognet.sharepoint.com</h3>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">
                Site: CognetStorage
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Document Library: <span className="font-medium text-foreground">Shared Documents</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isRunning ? (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-600 text-xs font-semibold animate-pulse">
              <CheckCircle2 className="w-4 h-4" /> Active & Polling ({isMultiFile ? "Subfolder Batch Mode" : "Single File Mode"})
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-muted text-muted-foreground text-xs font-semibold">
              <Square className="w-3.5 h-3.5" /> Idle / Stopped
            </span>
          )}
        </div>
      </div>

      {/* ─── CONFIGURATION & AUTOMATION CONTROLS ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Input & Output Config */}
        <Panel className="lg:col-span-2 p-5 space-y-4">
          <h3 className="text-sm font-semibold flex items-center gap-2 pb-2 border-b border-border">
            <FolderInput className="w-4 h-4 text-primary" />
            1. Folder & Engine Configuration
          </h3>

          <div className="space-y-4">
            {/* Input Folder */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Input SharePoint Folder Path
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <FolderInput className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={inputFolder}
                    onChange={(e) => setInputFolder(e.target.value)}
                    disabled={isRunning}
                    placeholder="Sales Support/Invoice To Census Automation"
                    className="w-full h-10 pl-9 pr-3 text-xs rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60 font-mono"
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={isRunning}
                  onClick={() => openPicker("input")}
                  title="Browse SharePoint Folders"
                  className="h-10 w-10 shrink-0 border border-input hover:bg-muted"
                >
                  <Search className="w-4 h-4 text-muted-foreground" />
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">
                SharePoint folder where incoming files or client subfolders arrive.
              </p>
            </div>

            {/* POC Engine Picker */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Select POC Processing Engine
              </label>
              <div className="relative">
                <Cpu className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <select
                  value={selectedEngine}
                  onChange={(e) => setSelectedEngine(e.target.value)}
                  disabled={isRunning}
                  className="w-full h-10 pl-9 pr-3 text-xs rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60 appearance-none"
                >
                  {ENGINE_GROUPS.map((grp) => (
                    <optgroup key={grp.groupLabel} label={grp.groupLabel}>
                      {grp.engines.map((eng) => (
                        <option key={eng.id} value={eng.id}>
                          {eng.name} [{eng.mode}]
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              {/* Mode indicator banner */}
              <div className={`mt-2 p-2.5 rounded-lg border text-xs flex items-start gap-2 ${
                ["renewal-process", "rpve"].includes(selectedEngine)
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-700 dark:text-purple-300"
                  : "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-300"
              }`}>
                <Info className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold">{currentEngineObj?.name} ({currentEngineObj?.mode})</div>
                  <div className="text-[11px] opacity-90 mt-0.5">{currentEngineObj?.desc}</div>
                  {["renewal-process", "rpve"].includes(selectedEngine) && (
                    <div className="text-[11px] font-medium mt-1 text-purple-800 dark:text-purple-200">
                      💡 <strong>Subfolder Mode Active:</strong> Place 2-3 related files inside client subfolders (e.g. <code>{inputFolder}/ClientA/</code>). The agent will process each subfolder as a single multi-file batch.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Output Folder */}
            <div>
              <label className="block text-xs font-semibold text-foreground mb-1.5">
                Output SharePoint Folder Path
              </label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <FolderOutput className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="text"
                    value={outputFolder}
                    onChange={(e) => setOutputFolder(e.target.value)}
                    disabled={isRunning}
                    placeholder="Sales Support/Processed_Outputs"
                    className="w-full h-10 pl-9 pr-3 text-xs rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60 font-mono"
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={isRunning}
                  onClick={() => openPicker("output")}
                  title="Browse SharePoint Folders"
                  className="h-10 w-10 shrink-0 border border-input hover:bg-muted"
                >
                  <Search className="w-4 h-4 text-muted-foreground" />
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">
                Folder on SharePoint where output JSON/Excel files will be uploaded.
              </p>
            </div>
          </div>
        </Panel>

        {/* Start / Stop Control Card */}
        <Panel className="p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold flex items-center gap-2 pb-2 border-b border-border">
              <Play className="w-4 h-4 text-emerald-500" />
              2. Automation Control
            </h3>
            <p className="text-xs text-muted-foreground mt-3 leading-relaxed">
              When started, the agent polls SharePoint every 10 seconds, downloads incoming files/subfolders, processes them with the selected engine, and uploads structured outputs back to SharePoint.
            </p>

            <div className="mt-4 p-3 rounded-lg bg-muted/40 border border-border space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Engine Mode:</span>
                <span className="font-semibold text-primary">
                  {["renewal-process", "rpve"].includes(selectedEngine) ? "📁 Subfolder Batch Mode" : "📄 Single File Mode"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Processed Count:</span>
                <span className="font-semibold text-foreground">{agent?.processed_count ?? 0} batches/files</span>
              </div>
            </div>
          </div>

          <div className="mt-6 pt-4 border-t border-border">
            {isRunning ? (
              <Button
                variant="destructive"
                className="w-full h-11 font-semibold"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
              >
                {stopMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Square className="w-4 h-4 mr-2" />}
                Stop SharePoint Automation
              </Button>
            ) : (
              <Button
                className="w-full h-11 font-semibold bg-emerald-600 hover:bg-emerald-700 text-white"
                onClick={() => startMutation.mutate()}
                disabled={startMutation.isPending || !inputFolder.trim()}
              >
                {startMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                Start SharePoint Automation
              </Button>
            )}
          </div>
        </Panel>
      </div>

      {/* ─── LIVE PROCESSING TABLE ─── */}
      <Panel className="overflow-hidden">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <h3 className="text-xs font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4 text-blue-500" />
            Processed Documents & Batches Log ({history.length})
          </h3>
        </div>

        {history.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            No items processed yet. Start automation above to begin polling SharePoint.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground font-medium">
                  <th className="px-4 py-2.5">Item / Batch Name</th>
                  <th className="px-4 py-2.5">Engine Used</th>
                  <th className="px-4 py-2.5">Output File</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Processed Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {history.map((row: any) => (
                  <tr key={row.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 font-medium text-foreground flex items-center gap-2">
                      {row.file_name.startsWith("Subfolder:") ? (
                        <FolderTree className="w-4 h-4 text-purple-500 shrink-0" />
                      ) : (
                        <Files className="w-4 h-4 text-blue-500 shrink-0" />
                      )}
                      <span>{row.file_name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded font-semibold text-[10px] ${
                        row.engine.includes("Batch")
                          ? "bg-purple-500/10 text-purple-600"
                          : "bg-primary/10 text-primary"
                      }`}>
                        {row.engine}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{row.output_name}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-600 font-semibold">
                        <CheckCircle2 className="w-3 h-3" /> {row.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{row.processed_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* ─── LIVE ACTIVITY LOG CONSOLE ─── */}
      <Panel className="p-4">
        <h3 className="text-xs font-semibold flex items-center gap-2 mb-3">
          <Terminal className="w-4 h-4 text-primary" />
          Live Agent Activity Console
        </h3>
        <div className="h-44 rounded-lg bg-slate-950 p-3 font-mono text-[11px] text-emerald-400 overflow-y-auto space-y-1">
          {logs.length === 0 ? (
            <div className="text-slate-500 italic">No logs generated yet...</div>
          ) : (
            logs.map((log: string, idx: number) => (
              <div key={idx} className="leading-relaxed">{log}</div>
            ))
          )}
        </div>
      </Panel>

      {/* ─── SHAREPOINT FOLDER PICKER MODAL ─── */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
              <Folder className="w-4 h-4 text-primary" />
              Select SharePoint Folder
            </DialogTitle>
            <DialogDescription className="text-xs">
              Choose a folder on SharePoint as the {pickerTarget === "input" ? "input source" : "output destination"}.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            {/* Breadcrumbs stack */}
            <div className="flex items-center flex-wrap gap-1 text-[11px] font-mono bg-muted/50 p-2 rounded-lg border border-border">
              {folderStack.map((item, idx) => (
                <span key={item.path || "root"} className="flex items-center gap-1">
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
            <div className="border border-border rounded-lg bg-background max-h-64 overflow-y-auto divide-y divide-border min-h-[180px]">
              {foldersQuery.isLoading ? (
                <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin text-primary" />
                  <span className="text-xs">Loading SharePoint folders...</span>
                </div>
              ) : foldersQuery.isError ? (
                <div className="text-xs text-destructive text-center py-12 px-4">
                  Failed to load SharePoint folders. Ensure you are logged in to Microsoft.
                </div>
              ) : !foldersQuery.data?.folders || foldersQuery.data.folders.length === 0 ? (
                <div className="text-xs text-muted-foreground text-center py-12">
                  No subfolders found inside this folder.
                </div>
              ) : (
                foldersQuery.data.folders.map((folder) => {
                  const isSelected = selectedPath === folder.path;
                  return (
                    <div
                      key={folder.id || folder.path}
                      onClick={() => handleSelectFolder(folder.path)}
                      onDoubleClick={() => handleEnterFolder(folder.path, folder.name, folder.id)}
                      className={cn(
                        "w-full text-left px-3 py-2.5 text-xs hover:bg-muted flex items-center justify-between gap-2 transition-colors cursor-pointer select-none",
                        isSelected && "bg-primary/10 text-primary font-medium"
                      )}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Folder className={cn("w-4 h-4 shrink-0 text-muted-foreground", isSelected && "text-primary")} />
                        <span className="truncate">{folder.name}</span>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEnterFolder(folder.path, folder.name, folder.id);
                        }}
                        className="h-6 text-[10px] px-2 text-muted-foreground hover:text-foreground shrink-0"
                      >
                        Open <ChevronRight className="w-3 h-3 ml-0.5" />
                      </Button>
                    </div>
                  );
                })
              )}
            </div>

            {selectedPath && (
              <div className="text-[11px] font-mono text-muted-foreground bg-muted/40 p-2 rounded border border-border truncate">
                Selected: <span className="text-foreground font-semibold">{selectedPath}</span>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" size="sm" onClick={() => setPickerOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleConfirmFolder}
              disabled={!selectedPath && !currentPath}
            >
              Select Folder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
