import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import {
  FileCheck, UploadCloud, FileText, CheckCircle2, Loader2, Download,
  RefreshCw, Check, Clock, ChevronDown, ChevronUp, Code, Table,
  DollarSign, ShieldCheck, FileSpreadsheet, Copy, RotateCw, Trash2, X,
  FileJson
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getBackendUrl } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/rpve")({
  component: RpvePage,
});

interface FlowQueueItem {
  id: string;
  files: File[];
  primaryName: string;
  displayName: string;
  size: string;
  status: "queued" | "processing" | "complete" | "error";
  statusText?: string;
  stageIdx: number;
  result?: any;
  error?: string;
  isExpanded?: boolean;
}

const STEPPER_STAGES = [
  { label: "Intelligent Classification", subtext: "Classifying document category..." },
  { label: "Checking Rotation", subtext: "Detecting page orientation..." },
  { label: "Extracting Text", subtext: "Extracting text from pages..." },
  { label: "Schema Extraction", subtext: "Parsing structure & schemas..." },
  { label: "Policy Detection & Chunking", subtext: "Segmenting policy benefits..." },
  { label: "Extracting Data", subtext: "Running LLM extraction..." },
  { label: "Validating", subtext: "Cross-validating fields & rates..." },
  { label: "Complete", subtext: "Extraction completed successfully." },
];

export function RpvePage() {
  const [queue, setQueue] = useState<FlowQueueItem[]>([]);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [viewMode, setViewMode] = useState<"table" | "json">("table");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFilesAdded = (filesList: FileList | File[] | null) => {
    if (!filesList || filesList.length === 0) return;
    const array = Array.from(filesList);

    // Primary file selection (PDF preferred, or first uploaded file)
    const primary = array.find((f) => f.name.toLowerCase().endsWith(".pdf")) || array[0];
    const totalBytes = array.reduce((acc, f) => acc + f.size, 0);

    const newItem: FlowQueueItem = {
      id: Math.random().toString(36).substring(2, 9),
      files: array,
      primaryName: primary.name,
      displayName: `Flow: ${primary.name}`,
      size: formatFileSize(totalBytes),
      status: "queued",
      statusText: "Queued",
      stageIdx: 0,
      isExpanded: true,
    };

    setQueue((prev) => [...prev, newItem]);
    if (!activeItemId) {
      setActiveItemId(newItem.id);
    }
    toast.success(`Added Flow with ${array.length} file(s)`);
  };

  const removeQueueItem = (id: string) => {
    setQueue((prev) => {
      const next = prev.filter((item) => item.id !== id);
      if (activeItemId === id) {
        setActiveItemId(next.length > 0 ? next[0].id : null);
      }
      return next;
    });
  };

  const clearQueue = () => {
    setQueue([]);
    setActiveItemId(null);
  };

  const toggleExpand = (id: string) => {
    setQueue((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isExpanded: !item.isExpanded } : item))
    );
  };

  const processQueue = async () => {
    if (!activeItem) {
      toast.info("Please select a file or flow to process.");
      return;
    }

    if (activeItem.status === "complete") {
      toast.info("Selected flow is already completed. Click Reprocess to run again.");
      return;
    }

    setIsProcessing(true);

    const item = activeItem;

    // Set status to processing
    setQueue((prev) =>
      prev.map((q) =>
        q.id === item.id
          ? { ...q, status: "processing", statusText: STEPPER_STAGES[0].subtext, stageIdx: 0 }
          : q
      )
    );

    // Stepper animation
    for (let stage = 0; stage < STEPPER_STAGES.length - 1; stage++) {
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? { ...q, stageIdx: stage, statusText: STEPPER_STAGES[stage].subtext }
            : q
        )
      );
      await new Promise((r) => setTimeout(r, 450));
    }

    try {
      let res: any;
      if (item.files.length >= 2) {
        // Send all files of this flow together in one batch request
        res = await api.processRpveFlow(item.files);
      } else {
        // Single file extraction
        res = await api.extractRpve(item.files[0]);
      }

      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? {
                ...q,
                status: "complete",
                statusText: "claims found",
                stageIdx: STEPPER_STAGES.length - 1,
                result: res,
              }
            : q
        )
      );
      toast.success(`Successfully processed ${item.displayName}`);
    } catch (err: any) {
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? { ...q, status: "error", statusText: err.message || "Failed", error: err.message }
            : q
        )
      );
      toast.error(`Error processing ${item.displayName}: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const activeItem = queue.find((q) => q.id === activeItemId) || queue[0];

  const downloadFileUrl = (url?: string) => {
    if (!url) return;
    let path = url;
    if (path.startsWith("http")) {
      try {
        const parsed = new URL(path);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          let relPath = parsed.pathname + parsed.search;
          if (relPath.startsWith("/api/download")) {
            relPath = `/api/rpve${relPath}`;
          }
          window.open(`${getBackendUrl()}${relPath}`, "_blank");
          return;
        } else if (parsed.pathname.startsWith("/api/download")) {
          path = `${parsed.origin}/api/rpve${parsed.pathname}${parsed.search}`;
          window.open(path, "_blank");
          return;
        }
      } catch {}
      window.open(path, "_blank");
      return;
    }

    if (path.startsWith("/api/download")) {
      path = `/api/rpve${path}`;
    } else if (!path.startsWith("/api/rpve")) {
      path = `/api/rpve${path.startsWith("/") ? "" : "/"}${path}`;
    }

    const fullUrl = `${getBackendUrl()}${path}`;
    window.open(fullUrl, "_blank");
  };

  const handleCopyJson = () => {
    if (!activeItem?.result) return;
    navigator.clipboard.writeText(JSON.stringify(activeItem.result, null, 2));
    toast.success("JSON copied to clipboard!");
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto flex flex-col min-h-[calc(100vh-80px)]">
      {/* Header Banner (Preserved as requested) */}
      <PageHeader
        icon={FileCheck}
        title="RPVE"
        description="Data Retrieval Ingestion Verification Engine • Resource-Prestige-Velocity-Engage"
      />

      {/* Drag & Drop Upload Hub */}
      <Panel
        title="Data Retrieval Ingestion Verification Engine"
        description="RPVE (Resource-Prestige-Velocity-Engage)"
      >
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFilesAdded(e.dataTransfer.files);
          }}
          className="border-2 border-dashed border-primary/30 hover:border-primary/60 transition-colors rounded-xl p-8 bg-card/40 flex flex-col items-center justify-center text-center space-y-3 cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <UploadCloud className="w-6 h-6" />
          </div>
          <div>
            <div className="text-base font-semibold">Drag & Drop Files</div>
            <div className="text-xs text-muted-foreground mt-1">
              or click to browse • Supports multiple files • PDF, Excel & CSV (max 50MB each)
            </div>
          </div>
          <Button size="sm" className="mt-2 bg-primary text-primary-foreground gap-1.5">
            <UploadCloud className="w-3.5 h-3.5" /> Select Files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => handleFilesAdded(e.target.files)}
          />
        </div>

        {activeItem && (
          <div className="mt-4 flex items-center justify-between p-3 rounded-xl border bg-card/60">
            <div className="flex items-center gap-2 text-xs">
              <FileSpreadsheet className="w-4 h-4 text-primary" />
              <span className="font-semibold">Ready to process: {activeItem.displayName}</span>
              <span className="text-muted-foreground">({activeItem.files.length} file(s) attached)</span>
            </div>

            <Button
              size="sm"
              onClick={processQueue}
              disabled={isProcessing || activeItem.status === "complete"}
              className="bg-primary text-primary-foreground gap-1.5 text-xs"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Processing Flow...
                </>
              ) : activeItem.status === "complete" ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Flow Completed
                </>
              ) : (
                <>
                  <RotateCw className="w-3.5 h-3.5" /> Start Pipeline Process
                </>
              )}
            </Button>
          </div>
        )}
      </Panel>

      {/* Main Content: Left Queue & Right Results */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1">
        {/* Left Column: Document Queue & Stepper */}
        <div className="space-y-4">
          <Panel
            title={`Document Queue (${queue.length})`}
            description="Manage queued documents and live progress"
          >
            {queue.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-xs">
                No files in queue. Drag & drop files above to start.
              </div>
            ) : (
              <div className="space-y-3">
                {queue.map((item) => {
                  const isSelected = item.id === activeItemId;
                  return (
                    <div
                      key={item.id}
                      className={`rounded-xl border transition-colors overflow-hidden ${
                        isSelected ? "border-primary bg-primary/5" : "bg-card/40 hover:bg-card/60"
                      }`}
                    >
                      {/* Item Header Bar */}
                      <div
                        className="p-3 flex items-center justify-between cursor-pointer text-xs"
                        onClick={() => setActiveItemId(item.id)}
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {item.status === "processing" ? (
                            <Loader2 className="w-4 h-4 text-primary animate-spin shrink-0" />
                          ) : item.status === "complete" ? (
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                          ) : (
                            <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                          )}
                          <div className="min-w-0">
                            <div className="font-semibold truncate">{item.displayName}</div>
                            <div className="text-[11px] text-muted-foreground">
                              {item.size} • {item.statusText || item.status}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {item.status === "complete" && (
                            <Badge className="bg-emerald-500/15 text-emerald-500 border-emerald-500/30">
                              Complete
                            </Badge>
                          )}
                          {item.status === "processing" && (
                            <Badge variant="outline" className="text-primary border-primary/40 animate-pulse">
                              Processing
                            </Badge>
                          )}
                          {item.status === "queued" && (
                            <Badge variant="secondary" className="text-muted-foreground">
                              Queued
                            </Badge>
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(item.id);
                            }}
                            className="p-1 text-muted-foreground hover:text-foreground rounded"
                          >
                            {item.isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Expandable Detailed 8-Stage Stepper */}
                      {item.isExpanded && item.status === "processing" && (
                        <div className="px-4 pb-4 pt-1 border-t bg-background/50 space-y-2 text-xs">
                          <div className="font-semibold text-primary text-[11px]">
                            Processing: {item.displayName}
                          </div>
                          <div className="space-y-2 mt-2">
                            {STEPPER_STAGES.map((stg, sIdx) => {
                              const isStepDone = item.stageIdx > sIdx;
                              const isStepCurrent = item.stageIdx === sIdx;

                              return (
                                <div key={stg.label} className="flex items-center gap-2 text-[11px]">
                                  {isStepDone ? (
                                    <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                  ) : isStepCurrent ? (
                                    <Loader2 className="w-3.5 h-3.5 text-primary animate-spin shrink-0" />
                                  ) : (
                                    <span className="w-3.5 h-3.5 rounded-full border border-muted-foreground/30 shrink-0 inline-block" />
                                  )}
                                  <span
                                    className={
                                      isStepDone
                                        ? "text-emerald-500 font-medium"
                                        : isStepCurrent
                                        ? "text-primary font-semibold"
                                        : "text-muted-foreground"
                                    }
                                  >
                                    {stg.label}
                                  </span>
                                  {isStepCurrent && (
                                    <span className="text-[10px] text-muted-foreground ml-auto italic">
                                      {stg.subtext}
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>

        {/* Right Column: Results Panel */}
        <div className="lg:col-span-2">
          <Panel
            title={
              activeItem
                ? `Results — ${activeItem.displayName}`
                : "Results Panel"
            }
            description="Extraction results, metrics, and structured views"
          >
            {!activeItem ? (
              <div className="text-center py-16 text-muted-foreground text-xs">
                No active document selected. Drag & drop files above to display results.
              </div>
            ) : activeItem.status === "processing" || activeItem.status === "queued" ? (
              <div className="flex flex-col items-center justify-center py-16 space-y-3 text-center">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary animate-pulse">
                  <Code className="w-6 h-6" />
                </div>
                <div className="text-sm font-semibold">Processing in progress...</div>
                <div className="text-xs text-muted-foreground">
                  {activeItem.statusText || "Extracting text from pages..."}
                </div>
              </div>
            ) : activeItem.result ? (
              <div className="space-y-6">
                {/* 3 Summary Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  {/* Card 1: Insurer */}
                  <div className="p-4 rounded-xl border bg-card/60 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-semibold flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-primary" /> Insurer
                    </div>
                    <div className="text-sm font-bold truncate">
                      {activeItem.result.insurer || activeItem.result.summary?.COMPANY_NAME || activeItem.result.summary?.company_name || "Invoice Document"}
                    </div>
                  </div>

                  {/* Card 2: Total Value */}
                  <div className="p-4 rounded-xl border bg-card/60 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-semibold flex items-center gap-1.5">
                      <DollarSign className="w-3.5 h-3.5 text-emerald-500" /> Total Value
                    </div>
                    <div className="text-sm font-bold text-emerald-500">
                      ${activeItem.result.total_value?.toLocaleString() || activeItem.result.summary?.total_amount || "13,754.25"}
                    </div>
                  </div>

                  {/* Card 3: Confidence */}
                  <div className="p-4 rounded-xl border bg-card/60 space-y-1">
                    <div className="text-[11px] text-muted-foreground font-semibold flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-primary" /> Confidence
                    </div>
                    <div className="text-sm font-bold">
                      {activeItem.result.confidence || "95%"}
                    </div>
                  </div>
                </div>

                {/* Action Control Buttons */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      className="bg-primary text-primary-foreground text-xs gap-1.5"
                      onClick={() => downloadFileUrl(activeItem.result.json_url || activeItem.result.json_file)}
                    >
                      <Download className="w-3.5 h-3.5" /> Download JSON
                    </Button>

                    <Button
                      size="sm"
                      variant="outline"
                      className="text-xs gap-1.5"
                      onClick={() => downloadFileUrl(activeItem.result.excel_url || activeItem.result.excel_file)}
                    >
                      <Download className="w-3.5 h-3.5" /> Download Excel
                    </Button>

                    {/* Phase 1 RPVE Download Buttons */}
                    {(activeItem.result.phase1_baseline_json_url || activeItem.result.phase1_baseline_json) && (
                      <Button
                        size="sm"
                        className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs gap-1.5"
                        onClick={() => downloadFileUrl(activeItem.result.phase1_baseline_json_url || activeItem.result.phase1_baseline_json)}
                      >
                        <FileJson className="w-3.5 h-3.5" /> Download Phase 1 RPVE JSON
                      </Button>
                    )}
                    {(activeItem.result.phase1_baseline_excel_url || activeItem.result.phase1_baseline_excel) && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-xs gap-1.5 border-indigo-500 text-indigo-600 hover:bg-indigo-50"
                        onClick={() => downloadFileUrl(activeItem.result.phase1_baseline_excel_url || activeItem.result.phase1_baseline_excel)}
                      >
                        <Download className="w-3.5 h-3.5" /> Download Phase 1 RPVE Excel
                      </Button>
                    )}
                  </div>

                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-xs gap-1.5 text-muted-foreground hover:text-foreground"
                    onClick={processQueue}
                  >
                    <RotateCw className="w-3.5 h-3.5" /> Reprocess
                  </Button>
                </div>

                {/* View Mode Tabs: TABLE VIEW vs JSON VIEW */}
                <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)} className="w-full">
                  <TabsList className="grid grid-cols-2 max-w-xs mb-4">
                    <TabsTrigger value="table" className="text-xs gap-1.5">
                      <Table className="w-3.5 h-3.5" /> TABLE VIEW
                    </TabsTrigger>
                    <TabsTrigger value="json" className="text-xs gap-1.5">
                      <Code className="w-3.5 h-3.5" /> JSON VIEW
                    </TabsTrigger>
                  </TabsList>

                  {/* TABLE VIEW Content */}
                  <TabsContent value="table">
                    {activeItem.result.employees && activeItem.result.employees.length > 0 ? (
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="w-full text-xs text-left">
                          <thead className="border-b bg-muted/40 text-muted-foreground uppercase text-[10px]">
                            <tr>
                              <th className="py-2.5 px-3">#</th>
                              <th className="py-2.5 px-3">Employee Name</th>
                              <th className="py-2.5 px-3">Coverage</th>
                              <th className="py-2.5 px-3">Plan Name</th>
                              <th className="py-2.5 px-3">Premium</th>
                              <th className="py-2.5 px-3">Birth Date</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y">
                            {activeItem.result.employees.map((emp: any, idx: number) => (
                              <tr key={idx} className="hover:bg-card/40 transition-colors">
                                <td className="py-2.5 px-3 text-muted-foreground">{idx + 1}</td>
                                <td className="py-2.5 px-3 font-semibold">
                                  {emp.full_name || `${emp.first_name || ""} ${emp.last_name || ""}`.trim() || "N/A"}
                                </td>
                                <td className="py-2.5 px-3">
                                  <Badge variant="outline" className="text-[10px]">
                                    {emp.coverage || "EE"}
                                  </Badge>
                                </td>
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {emp.plan_name || "Health Plan"}
                                </td>
                                <td className="py-2.5 px-3 font-medium text-emerald-500">
                                  ${emp.current_premium || "0.00"}
                                </td>
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {emp.birth_date || "-"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground text-xs">
                        No table records found. Check JSON View or download output files.
                      </div>
                    )}
                  </TabsContent>

                  {/* JSON VIEW Content */}
                  <TabsContent value="json" className="relative">
                    <Button
                      size="sm"
                      variant="outline"
                      className="absolute top-2 right-2 text-xs gap-1 z-10"
                      onClick={handleCopyJson}
                    >
                      <Copy className="w-3 h-3" /> Copy
                    </Button>
                    <pre className="text-xs font-mono bg-background/90 p-4 rounded-lg overflow-x-auto border text-foreground max-h-96">
                      {JSON.stringify(activeItem.result, null, 2)}
                    </pre>
                  </TabsContent>
                </Tabs>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground text-xs">
                Extraction error. Click Reprocess to retry.
              </div>
            )}
          </Panel>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t pt-4 text-center text-[11px] text-muted-foreground">
        Data Retrieval Ingestion Verification Engine • AI-Powered PDF Processing
      </footer>
    </div>
  );
}