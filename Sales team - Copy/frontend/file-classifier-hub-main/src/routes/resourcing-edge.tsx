import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect, useCallback } from "react";
import {
  Cpu, UploadCloud, FileText, Loader2, Download,
  Copy, Layers, Sparkles, Check, Code, ShieldCheck,
  History, FileJson, AlertCircle, RefreshCw, Clock
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getBackendUrl, type ResourcingHistoryRecord } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/resourcing-edge")({
  component: ResourcingEdgePage,
});

const PIPELINE_STAGES = [
  { label: "Document Verification", desc: "Checking PDF format & digital text layer" },
  { label: "Text & Table Extraction", desc: "Parsing benefit matrices & rates" },
  { label: "LLM Field Parsing", desc: "Structuring health plan attributes" },
  { label: "JSON Schema Generation", desc: "Validating against target schema" },
];

function StatusBadge({ status }: { status: string }) {
  const isSuccess = status.toUpperCase() === "SUCCESS";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
        isSuccess
          ? "bg-emerald-500/15 text-emerald-500"
          : "bg-red-500/15 text-red-500"
      }`}
    >
      {isSuccess ? <Check className="w-2.5 h-2.5" /> : <AlertCircle className="w-2.5 h-2.5" />}
      {isSuccess ? "Success" : "Failed"}
    </span>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function ResourcingEdgePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [stageIdx, setStageIdx] = useState(0);
  const [resultData, setResultData] = useState<any | null>(null);
  const [activeTab, setActiveTab] = useState("summary");

  const [history, setHistory] = useState<ResourcingHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const rows = await api.getResourcingHistory(50);
      setHistory(rows);
    } catch {
      // silently ignore — backend may not yet have any records
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const handleFileDrop = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are supported for Resourcing Edge.");
      return;
    }
    setSelectedFile(file);
    toast.success(`Loaded file: ${file.name}`);
  };

  const runPipeline = async () => {
    if (!selectedFile) {
      toast.error("Please select a PDF file first.");
      return;
    }

    setIsProcessing(true);
    setStageIdx(0);

    try {
      setStageIdx(0);
      await new Promise((r) => setTimeout(r, 600));

      setStageIdx(1);
      await new Promise((r) => setTimeout(r, 800));

      setStageIdx(2);
      const res = await api.processResourcingPdf(selectedFile);

      setStageIdx(3);
      setResultData(res);
      toast.success("Insurance plan parsed successfully!");
      // Refresh history after successful run
      setTimeout(fetchHistory, 1000);
    } catch (err: any) {
      toast.error(`Parsing error: ${err.message || "Failed to process PDF"}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyJson = () => {
    if (!resultData) return;
    navigator.clipboard.writeText(JSON.stringify(resultData, null, 2));
    toast.success("JSON copied to clipboard");
  };

  const handleDownloadJson = () => {
    if (!selectedFile || !resultData) return;
    const stem = selectedFile.name.replace(/\.[^/.]+$/, "");
    const blob = new Blob([JSON.stringify(resultData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stem}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /** Download a historical JSON by its pdf_stem from the backend /download endpoint */
  const handleHistoryDownload = (record: ResourcingHistoryRecord) => {
    // Derive the stem from output_json field (e.g. "structure.json" → "structure")
    // or fall back to pdf_filename stem
    const stem = record.output_json
      ? record.output_json.replace(/\.json$/i, "")
      : record.pdf_filename.replace(/\.[^/.]+$/, "");

    const url = api.downloadResourcingJsonUrl(stem);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${stem}.json`;
    a.click();
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <PageHeader
        icon={Cpu}
        title="Resourcing Edge"
        description="Automated Insurance Plan & Benefit PDF Extraction Engine"
      />

      {/* Upload Panel */}
      <Panel
        title="Insurance Plan Upload"
        description="Drop a Resourcing Edge insurance plan document (PDF) to run full schema extraction."
      >
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            handleFileDrop(e.dataTransfer.files);
          }}
          className="border-2 border-dashed border-primary/30 hover:border-primary/60 transition-colors rounded-xl p-8 bg-card/40 flex flex-col items-center justify-center text-center space-y-3 cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
        >
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
            <UploadCloud className="w-6 h-6" />
          </div>
          <div>
            <div className="text-base font-semibold">
              {selectedFile ? selectedFile.name : "Drag & Drop Insurance Plan PDF"}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Supports Resourcing Edge benefit SBCs, Rate sheets & Plan summaries (PDF only)
            </div>
          </div>
          <Button size="sm" variant={selectedFile ? "outline" : "default"} className="mt-1">
            {selectedFile ? "Change PDF File" : "Select PDF File"}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={(e) => handleFileDrop(e.target.files)}
          />
        </div>

        {/* Execute Bar */}
        {selectedFile && (
          <div className="mt-4 flex items-center justify-between p-3 rounded-lg border bg-card/60">
            <div className="flex items-center gap-2 text-xs">
              <FileText className="w-4 h-4 text-primary" />
              <span className="font-medium">{selectedFile.name}</span>
              <span className="text-muted-foreground">
                ({(selectedFile.size / (1024 * 1024)).toFixed(2)} MB)
              </span>
            </div>
            <Button
              size="sm"
              onClick={runPipeline}
              disabled={isProcessing}
              className="bg-primary text-primary-foreground gap-1.5 text-xs"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Extracting Schema...
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" /> Parse Insurance Plan
                </>
              )}
            </Button>
          </div>
        )}
      </Panel>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Results Viewer */}
        <div className="lg:col-span-2">
          <Panel
            title="Extraction Results"
            description="Structured JSON output and benefit summary"
            action={
              resultData && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="text-xs gap-1.5" onClick={handleCopyJson}>
                    <Copy className="w-3.5 h-3.5" /> Copy
                  </Button>
                  <Button size="sm" className="text-xs gap-1.5 bg-primary text-primary-foreground" onClick={handleDownloadJson}>
                    <Download className="w-3.5 h-3.5" /> Download JSON
                  </Button>
                </div>
              )
            }
          >
            {resultData ? (
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="grid grid-cols-2 mb-4">
                  <TabsTrigger value="summary" className="text-xs">
                    <Layers className="w-3.5 h-3.5 mr-1.5" /> Plan Overview
                  </TabsTrigger>
                  <TabsTrigger value="json" className="text-xs">
                    <Code className="w-3.5 h-3.5 mr-1.5" /> Raw JSON Schema
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="summary" className="space-y-4">
                  {/* Metric Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <div className="p-3 rounded-lg border bg-card/40 space-y-1">
                      <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                        Carrier Name
                      </div>
                      <div className="text-xs font-semibold truncate">
                        {resultData.carrier_name || resultData.carrier || "Resourcing Edge"}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border bg-card/40 space-y-1">
                      <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                        Plan Name
                      </div>
                      <div className="text-xs font-semibold truncate">
                        {resultData.plan_name || resultData.plan || "Standard PPO Plan"}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border bg-card/40 space-y-1">
                      <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                        Network Type
                      </div>
                      <div className="text-xs font-semibold">
                        {resultData.network_type || "PPO / In-Network"}
                      </div>
                    </div>
                  </div>

                  {/* Summary Details */}
                  <div className="p-4 rounded-lg border bg-card/30 space-y-2">
                    <div className="text-xs font-semibold flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-500" /> Key Benefits & Coverage
                    </div>
                    <pre className="text-xs font-mono bg-background/80 p-3 rounded-md overflow-x-auto text-muted-foreground max-h-60">
                      {JSON.stringify(
                        resultData.benefits || resultData.summary || resultData,
                        null,
                        2
                      )}
                    </pre>
                  </div>
                </TabsContent>

                <TabsContent value="json">
                  <pre className="text-xs font-mono bg-background/90 p-4 rounded-lg overflow-x-auto border text-foreground max-h-96">
                    {JSON.stringify(resultData, null, 2)}
                  </pre>
                </TabsContent>
              </Tabs>
            ) : (
              <div className="text-center py-12 text-muted-foreground text-xs">
                No parsed data yet. Upload a Resourcing Edge PDF above to process.
              </div>
            )}
          </Panel>
        </div>

        {/* Live Stepper */}
        <div>
          <Panel title="Pipeline Execution" description="Processing steps">
            <div className="space-y-4 py-2">
              {PIPELINE_STAGES.map((stage, idx) => {
                const isDone = isProcessing ? idx < stageIdx : resultData !== null;
                const isCurrent = isProcessing && idx === stageIdx;

                return (
                  <div key={stage.label} className="flex items-start gap-3">
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs ${
                        isDone
                          ? "bg-primary text-primary-foreground"
                          : isCurrent
                          ? "bg-primary/20 text-primary border border-primary animate-pulse"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {isDone ? (
                        <Check className="w-3.5 h-3.5" />
                      ) : isCurrent ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        idx + 1
                      )}
                    </div>
                    <div>
                      <div className="text-xs font-semibold">{stage.label}</div>
                      <div className="text-[11px] text-muted-foreground">{stage.desc}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      </div>

      {/* ── Processing History ─────────────────────────────────────────────── */}
      <Panel
        title="Processing History"
        description="Previous Resourcing Edge extraction runs"
        action={
          <Button
            size="sm"
            variant="outline"
            className="text-xs gap-1.5"
            onClick={fetchHistory}
            disabled={historyLoading}
          >
            {historyLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            Refresh
          </Button>
        }
      >
        {historyLoading && history.length === 0 ? (
          <div className="flex items-center justify-center py-10 gap-2 text-muted-foreground text-xs">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading history...
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-10 text-muted-foreground text-xs">
            <History className="w-8 h-8 mx-auto mb-2 opacity-30" />
            No processing runs yet. Parse a PDF above to get started.
          </div>
        ) : (
          <div className="space-y-2">
            {history.map((record, i) => (
              <div
                key={record.id}
                className="flex items-center justify-between gap-3 p-3 rounded-lg border bg-card/40 hover:bg-card/70 transition-colors group"
              >
                {/* Icon + file info */}
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <FileJson className="w-4 h-4 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-semibold truncate max-w-xs" title={record.pdf_filename}>
                      {record.pdf_filename}
                    </div>
                    {record.plan_names && (
                      <div className="text-[11px] text-muted-foreground truncate max-w-xs" title={record.plan_names}>
                        {record.plan_names}
                      </div>
                    )}
                    {record.error_message && record.status.toUpperCase() !== "SUCCESS" && (
                      <div className="text-[11px] text-red-400 truncate max-w-xs" title={record.error_message}>
                        {record.error_message}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right side: run index, status, date, download */}
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-[10px] text-muted-foreground hidden sm:block">
                    Run #{history.length - i}
                  </span>
                  <StatusBadge status={record.status} />
                  <div className="hidden md:flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {formatDate(record.created_date)}
                  </div>
                  {record.status.toUpperCase() === "SUCCESS" && record.output_json && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={() => handleHistoryDownload(record)}
                      title="Download extracted JSON"
                    >
                      <Download className="w-3 h-3" />
                      <span className="hidden sm:inline">JSON</span>
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
