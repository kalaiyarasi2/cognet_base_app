import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import {
  RefreshCw, FileSpreadsheet, FileText, CheckCircle2,
  Loader2, Download, Check, Sparkles, BookOpen
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, getBackendUrl } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/renewal-process")({
  component: RenewalProcessPage,
});

interface JobResult {
  job_id: string;
  status: "pending" | "processing" | "success" | "failed";
  invoice_name: string;
  census_name: string;
  created_at: number;
  completed_at?: number;
  download_url?: string;
  rates_json_url?: string;
  error?: string;
}

const STAGES = [
  { id: "census", label: "Census Ingestion", desc: "Ingesting current employee census" },
  { id: "invoice", label: "Invoice Ingestion", desc: "Extracting renewal rates via LLM/OCR" },
  { id: "matching", label: "Data Matching", desc: "Cross-referencing members to plans & tiers" },
  { id: "summary", label: "Renewal Summary", desc: "Generating updated census roster" },
];

export function RenewalProcessPage() {
  const [censusFile, setCensusFile] = useState<File | null>(null);
  const [invoiceFile, setInvoiceFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [stageIdx, setStageIdx] = useState(0);
  const [activeJob, setActiveJob] = useState<JobResult | null>(null);
  const [jobHistory, setJobHistory] = useState<JobResult[]>([]);

  const censusInputRef = useRef<HTMLInputElement>(null);
  const invoiceInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    try {
      const data = await api.getRenewalJobs();
      if (Array.isArray(data)) {
        setJobHistory(data);
        if (data.length > 0 && !activeJob) {
          setActiveJob(data[0]);
        }
      }
    } catch {
      // Backend may not have runs yet
    }
  };

  const downloadFileUrl = (url?: string) => {
    if (!url) return;
    let path = url;
    if (path.startsWith("http")) {
      try {
        const parsed = new URL(path);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          let relPath = parsed.pathname + parsed.search;
          if (relPath.startsWith("/output")) {
            relPath = `/api/renewal${relPath}`;
          }
          window.open(`${getBackendUrl()}${relPath}`, "_blank");
          return;
        } else if (parsed.pathname.startsWith("/output")) {
          path = `${parsed.origin}/api/renewal${parsed.pathname}${parsed.search}`;
          window.open(path, "_blank");
          return;
        }
      } catch {}
      window.open(path, "_blank");
      return;
    }
    if (path.startsWith("/output")) {
      path = `/api/renewal${path}`;
    } else if (!path.startsWith("/api/renewal")) {
      path = `/api/renewal${path.startsWith("/") ? "" : "/"}${path}`;
    }
    const fullUrl = `${getBackendUrl()}${path}`;
    window.open(fullUrl, "_blank");
  };

  const handleProcessRenewal = async () => {
    if (!censusFile || !invoiceFile) {
      toast.error("Please upload both Census File and Renewal Invoice.");
      return;
    }

    setIsProcessing(true);
    setStageIdx(0);

    try {
      // Stage 1: Census Ingestion
      setStageIdx(0);
      const initialJob = await api.processRenewal(censusFile, invoiceFile);

      // Poll until finished (increased max attempts to 600 = 15 minutes)
      const jobId = initialJob.job_id;
      let finished = false;
      let attempts = 0;

      while (!finished && attempts < 600) {
        await new Promise((r) => setTimeout(r, 1500));
        attempts++;

        const current = await api.getRenewalJob(jobId);
        setActiveJob(current);

        if (current.status === "processing") {
          if (attempts > 2) setStageIdx(1);
          if (attempts > 12) setStageIdx(2);
          if (attempts > 30) setStageIdx(3);
        } else if (current.status === "success" || current.status === "failed") {
          finished = true;
          setStageIdx(3);
          if (current.status === "success") {
            toast.success("Renewal processed successfully!");
          } else {
            toast.error(`Renewal failed: ${current.error || "Processing failed"}`);
          }
        }
      }

      fetchHistory();
    } catch (err: any) {
      toast.error(`Error processing renewal: ${err.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header with Engine Badge & Docs link */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <PageHeader
          icon={RefreshCw}
          title="Census Creation"
          description="Automated matching of employee census rosters with carrier benefit renewal rates."
        />
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/30 gap-1.5 py-1 px-2.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            Engine: Renewal v2 Active
          </Badge>
          <Button variant="outline" size="sm" className="gap-1 text-xs">
            <BookOpen className="w-3.5 h-3.5" /> Docs
          </Button>
        </div>
      </div>

      {/* Dual Upload Hub */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: Census File */}
        <Panel
          title="1. Census File"
          description="Upload the current employee census roster."
        >
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) setCensusFile(e.dataTransfer.files[0]);
            }}
            className="border-2 border-dashed border-primary/20 hover:border-primary/50 transition-colors rounded-xl p-6 bg-card/40 flex flex-col items-center justify-center text-center space-y-3 cursor-pointer"
            onClick={() => censusInputRef.current?.click()}
          >
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-semibold">
                {censusFile ? censusFile.name : "Drag & drop your file here"}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                or click to browse · CSV, Excel & PDF · max 50MB
              </div>
            </div>
            <Button size="sm" variant={censusFile ? "outline" : "default"} className="text-xs">
              {censusFile ? "Change File" : "Select File"}
            </Button>
            <input
              ref={censusInputRef}
              type="file"
              accept=".xlsx,.xls,.csv,.pdf"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && setCensusFile(e.target.files[0])}
            />
          </div>
        </Panel>

        {/* Card 2: Renewal Invoice */}
        <Panel
          title="2. Renewal Invoice"
          description="Upload the renewal invoice issued by the carrier."
        >
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files[0]) setInvoiceFile(e.dataTransfer.files[0]);
            }}
            className="border-2 border-dashed border-primary/20 hover:border-primary/50 transition-colors rounded-xl p-6 bg-card/40 flex flex-col items-center justify-center text-center space-y-3 cursor-pointer"
            onClick={() => invoiceInputRef.current?.click()}
          >
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-semibold">
                {invoiceFile ? invoiceFile.name : "Drag & drop your file here"}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">
                or click to browse · PDF, Word & Images · max 50MB
              </div>
            </div>
            <Button size="sm" variant={invoiceFile ? "outline" : "default"} className="text-xs">
              {invoiceFile ? "Change File" : "Select File"}
            </Button>
            <input
              ref={invoiceInputRef}
              type="file"
              accept=".pdf,.docx,.doc,.jpg,.jpeg,.png"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && setInvoiceFile(e.target.files[0])}
            />
          </div>
        </Panel>
      </div>

      {/* Process Action Bar */}
      <div className="flex items-center justify-between p-4 rounded-xl border bg-card/60">
        <span className="text-xs text-muted-foreground">
          {!censusFile || !invoiceFile
            ? "Upload both files to enable processing."
            : "Both files ready. Click Process Renewal to start audit."}
        </span>
        <Button
          onClick={handleProcessRenewal}
          disabled={!censusFile || !invoiceFile || isProcessing}
          className="bg-primary text-primary-foreground gap-2"
        >
          {isProcessing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" /> Processing Renewal...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" /> Process Renewal
            </>
          )}
        </Button>
      </div>

      {/* Results & Live Progress Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Renewal Results Card */}
        <div className="lg:col-span-2 space-y-6">
          <Panel
            title="Renewal Results"
            description="Structured renewal summary ready for review and export."
          >
            {activeJob ? (
              <div className="space-y-4">
                {/* Status banner */}
                <div
                  className={`flex items-center justify-between p-3 rounded-lg border text-xs font-medium ${
                    activeJob.status === "success"
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-500"
                      : activeJob.status === "processing"
                      ? "bg-primary/10 border-primary/30 text-primary animate-pulse"
                      : "bg-destructive/10 border-destructive/30 text-destructive"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {activeJob.status === "success" ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : activeJob.status === "processing" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <FileText className="w-4 h-4" />
                    )}
                    <span>
                      {activeJob.status === "success"
                        ? "Renewal processed successfully"
                        : activeJob.status === "processing"
                        ? "Renewal audit processing in progress..."
                        : `Processing failed: ${activeJob.error || "Unknown error"}`}
                    </span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">
                    {new Date(activeJob.created_at * 1000).toLocaleString()}
                  </span>
                </div>

                {/* File Pills */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg border bg-card/40 flex items-center gap-3 text-xs">
                    <FileText className="w-4 h-4 text-primary shrink-0" />
                    <div className="min-w-0">
                      <div className="text-[10px] text-muted-foreground font-semibold uppercase">
                        Renewal Invoice
                      </div>
                      <div className="font-medium truncate">{activeJob.invoice_name}</div>
                    </div>
                  </div>

                  <div className="p-3 rounded-lg border bg-card/40 flex items-center gap-3 text-xs">
                    <FileSpreadsheet className="w-4 h-4 text-primary shrink-0" />
                    <div className="min-w-0">
                      <div className="text-[10px] text-muted-foreground font-semibold uppercase">
                        Census File
                      </div>
                      <div className="font-medium truncate">{activeJob.census_name}</div>
                    </div>
                  </div>
                </div>

                {/* Download Actions */}
                <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
                  {activeJob.rates_json_url && activeJob.status === "success" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-xs gap-1.5"
                      onClick={() => downloadFileUrl(activeJob.rates_json_url)}
                    >
                      <Download className="w-3.5 h-3.5 text-primary" /> Download Extracted Rates (JSON)
                    </Button>
                  )}
                  {activeJob.download_url && activeJob.status === "success" && (
                    <Button
                      size="sm"
                      className="text-xs gap-1.5 bg-primary text-primary-foreground"
                      onClick={() => downloadFileUrl(activeJob.download_url)}
                    >
                      <Download className="w-3.5 h-3.5" /> Download Updated Census
                    </Button>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-10 text-muted-foreground text-xs">
                No renewal results available. Upload census and invoice files above to start.
              </div>
            )}
          </Panel>

          {/* Processing History Card */}
          <Panel
            title="Processing History"
            description="Recent runs in system"
            action={<span className="text-xs text-muted-foreground">Recent</span>}
          >
            {jobHistory.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground text-xs">
                No past runs recorded.
              </div>
            ) : (
              <div className="space-y-2">
                {jobHistory.map((j, idx) => (
                  <div
                    key={j.job_id}
                    onClick={() => setActiveJob(j)}
                    className={`p-3 rounded-lg border text-xs cursor-pointer transition-colors ${
                      activeJob?.job_id === j.job_id
                        ? "border-primary bg-primary/5"
                        : "hover:bg-card/40"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="font-semibold text-xs">Run #{jobHistory.length - idx}</div>
                      <Badge
                        className={
                          j.status === "success"
                            ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/30"
                            : j.status === "processing"
                            ? "bg-primary/15 text-primary border-primary/30"
                            : "bg-destructive/15 text-destructive border-destructive/30"
                        }
                      >
                        {j.status === "success"
                          ? "Completed"
                          : j.status === "processing"
                          ? "Processing"
                          : "Failed"}
                      </Badge>
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1 space-y-0.5">
                      <div>Census: {j.census_name}</div>
                      <div>Invoice: {j.invoice_name}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        {/* Renewal Pipeline Live Progress Card */}
        <div>
          <Panel title="Renewal Pipeline" description="Live progress">
            <div className="space-y-5 py-2">
              {STAGES.map((stage, idx) => {
                const isDone = isProcessing ? idx < stageIdx : activeJob?.status === "success";
                const isCurrent = isProcessing && idx === stageIdx;

                return (
                  <div key={stage.id} className="flex items-start gap-3">
                    <div
                      className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs ${
                        isDone
                          ? "bg-emerald-500 text-white"
                          : isCurrent
                          ? "bg-primary text-primary-foreground animate-pulse"
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
    </div>
  );
}
