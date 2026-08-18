import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useCallback } from "react";
import {
  FileText, UploadCloud, Loader2, Download, CheckCircle2, AlertCircle,
  FileJson, Table2, X, Copy, Calendar, Hash, Percent, DollarSign,
  MapPin, ShieldAlert, ScanLine, FileSpreadsheet, Layers, RefreshCw
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import { useAuth } from "@/lib/store";

export const Route = createFileRoute("/psh-claim-extractor")({
  component: PshClaimExtractorPage,
});

// ─── Base-claim- app is mounted at /claim on the main backend (port 8000) ─────
const PSH_BACKEND_URL = "";
const PSH_CLAIM_PREFIX = "/claim";

// ─── Field metadata matching EXPECTED_KEYS in claim_dual_extractor.py ────────
const FIELD_META: Record<string, { label: string; icon: any }> = {
  claim_sui_account_number:   { label: "SUI Account Number",       icon: Hash },
  claimant_ssn:               { label: "Claimant SSN",             icon: ShieldAlert },
  claimant_name:              { label: "Claimant Name",            icon: FileText },
  claim_start_date:           { label: "Claim Start Date",         icon: Calendar },
  claim_end_date:             { label: "Claim End Date",           icon: Calendar },
  byb_date:                   { label: "BYB Date",                 icon: Calendar },
  bye_date:                   { label: "BYE Date",                 icon: Calendar },
  claim_mailing_date:         { label: "Mailing Date",             icon: Calendar },
  claim_liability_percentage: { label: "Liability %",              icon: Percent },
  claim_liability_base_amount:{ label: "Liability Base Amount",   icon: DollarSign },
  agency_address_line_1:      { label: "Agency Address Line 1",    icon: MapPin },
  agency_address_line_2:      { label: "Agency Address Line 2",    icon: MapPin },
  separation_code:            { label: "Separation Code",          icon: ScanLine },
  calculated_claim_liability: { label: "Calculated Claim Liability", icon: DollarSign },
};

const FIELD_KEYS = Object.keys(FIELD_META);

// ─── Processing stages ────────────────────────────────────────────────────────
const STAGES = [
  { label: "PDF Verified",         sub: "Document format validated successfully." },
  { label: "GPT Vision Running",   sub: "Analyzing PDF pages with Vision OCR..." },
  { label: "Generating Report",    sub: "Building Excel & JSON outputs..." },
  { label: "Complete",             sub: "Extraction finished successfully." },
];

type Status = "idle" | "processing" | "complete" | "error";

interface ExtractionResult {
  subfolder: string;
  txt_path: string;
  json_path: string;
  excel_path: string;
  data: Record<string, string>[];
  audit_logs?: Record<string, any>[];
  case_name?: string;
  excel_download_url?: string;
  json_download_url?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmtSize = (b: number) =>
  b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`;

// ─── Main Component ───────────────────────────────────────────────────────────
function PshClaimExtractorPage() {
  const [file, setFile]             = useState<File | null>(null);
  const [status, setStatus]         = useState<Status>("idle");
  const [stageIdx, setStageIdx]     = useState(0);
  const [result, setResult]         = useState<ExtractionResult | null>(null);
  const [error, setError]           = useState<string | null>(null);
  const [viewMode, setViewMode]     = useState<"table" | "json">("table");
  const [selectedPage, setSelectedPage] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef                = useRef<HTMLInputElement>(null);
  const { user } = useAuth();

  // ── File handlers ─────────────────────────────────────────────────────────
  const handleFile = (f: File) => {
    if (!f.name.toLowerCase().endsWith(".pdf") && f.type !== "application/pdf") {
      toast.error("Only PDF files (.pdf) are supported.");
      return;
    }
    setFile(f);
    setStatus("idle");
    setResult(null);
    setError(null);
    setStageIdx(0);
    setSelectedPage(0);
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }, []);

  const clearFile = () => {
    setFile(null);
    setStatus("idle");
    setResult(null);
    setError(null);
    setStageIdx(0);
    setSelectedPage(0);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ── Run extraction ────────────────────────────────────────────────────────
  const runExtraction = async () => {
    if (!file) return;
    setStatus("processing");
    setError(null);
    setResult(null);
    setStageIdx(0);

    const formData = new FormData();
    formData.append("file", file);

    try {
      setStageIdx(1);
      
      const interval = setInterval(() => {
        setStageIdx((prev) => (prev < 2 ? prev + 1 : prev));
      }, 4000);

      const res = await fetch(`${PSH_BACKEND_URL}${PSH_CLAIM_PREFIX}/api/extract-claim-pdf`, {
        method: "POST",
        headers: {
          "X-Processed-By": user?.email || "SYSTEM"
        },
        body: formData,
      });

      clearInterval(interval);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Extraction failed");
      }

      setStageIdx(3);
      const data: ExtractionResult = await res.json();
      setResult(data);
      setStatus("complete");

      const pageCount = data.data?.length || 0;
      toast.success(`Claim Extraction Complete — Extracted ${pageCount} page(s) successfully!`);
    } catch (err: any) {
      setError(err.message || "Unknown error");
      setStatus("error");
      toast.error("Extraction failed: " + (err.message || "Unknown error"));
    }
  };

  // ── Downloads ──────────────────────────────────────────────────────────────
  const downloadExcel = () => {
    if (!result?.excel_download_url) {
      toast.error("Excel download link not available.");
      return;
    }
    const fullUrl = `${PSH_BACKEND_URL}${PSH_CLAIM_PREFIX}${result.excel_download_url}`;
    window.open(fullUrl, "_blank");
    toast.success("Downloading Excel Validation Report...");
  };

  const downloadJson = () => {
    if (!result?.json_download_url) {
      toast.error("JSON download link not available.");
      return;
    }
    const fullUrl = `${PSH_BACKEND_URL}${PSH_CLAIM_PREFIX}${result.json_download_url}`;
    window.open(fullUrl, "_blank");
    toast.success("Downloading Extracted JSON File...");
  };

  const copyJson = () => {
    if (!result?.data) return;
    navigator.clipboard.writeText(JSON.stringify(result.data, null, 2));
    toast.success("JSON data copied to clipboard!");
  };

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <>
      <PageHeader
        icon={FileText}
        title="PSH-UI Claim Extractor"
        description="Upload an Unemployment Claim PDF document. GPT Vision & Dual Engine extract structured claim data page-by-page."
        actions={
          result ? (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={copyJson} className="gap-1.5">
                <Copy className="w-3.5 h-3.5" /> Copy JSON
              </Button>
              <Button size="sm" variant="default" onClick={downloadExcel} className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white">
                <FileSpreadsheet className="w-3.5 h-3.5" /> Download Excel
              </Button>
            </div>
          ) : null
        }
      />

      <div className="p-6 max-w-7xl mx-auto">
        {/* ── 2-Column Split Layout matching PSH-UI Claim Validator ───────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* ── LEFT COLUMN: Persistent Upload & Progress Controls ───────────── */}
          <div className="lg:col-span-5 space-y-5">
            {/* Upload Card */}
            <Panel className="p-5">
              <div className="mb-3">
                <h3 className="text-sm font-semibold">Upload PDF Document</h3>
                <p className="text-xs text-muted-foreground">Unemployment Claim PDF document file (.pdf)</p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={onInputChange}
                className="hidden"
              />

              {!file ? (
                <div
                  onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={onDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                    isDragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/30"
                  }`}
                >
                  <div className="w-12 h-12 rounded-full bg-primary/10 text-primary grid place-items-center mx-auto mb-2">
                    <UploadCloud className="w-6 h-6" />
                  </div>
                  <p className="text-xs font-medium">Click to upload or drag & drop</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">Supports PDF documents (.pdf)</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/20">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-8 h-8 rounded-md bg-red-500/10 text-red-600 grid place-items-center shrink-0">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-medium truncate">{file.name}</p>
                        <p className="text-[10px] text-muted-foreground">{fmtSize(file.size)}</p>
                      </div>
                    </div>
                    {status !== "processing" && (
                      <Button size="icon" variant="ghost" onClick={clearFile} className="h-7 w-7 text-muted-foreground hover:text-foreground">
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    )}
                  </div>

                  {/* Run Extraction Button inside upload panel */}
                  <Button
                    onClick={runExtraction}
                    disabled={status === "processing"}
                    className="w-full gap-2 bg-primary hover:bg-primary/90 text-xs py-2 h-9"
                  >
                    {status === "processing" ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Processing...
                      </>
                    ) : (
                      <>
                        <FileText className="w-3.5 h-3.5" /> Run Extraction
                      </>
                    )}
                  </Button>
                </div>
              )}

              <div className="mt-3 pt-2 border-t flex items-center justify-between text-[11px] text-muted-foreground">
                <span>Connected to:</span>
                <code className="bg-muted px-1.5 py-0.5 rounded text-[10px]">{PSH_BACKEND_URL}{PSH_CLAIM_PREFIX}</code>
              </div>
            </Panel>

            {/* Stage Tracker Panel */}
            <Panel className="p-5">
              <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Extraction Progress
              </h3>

              <div className="space-y-3">
                {STAGES.map((stg, idx) => {
                  const isDone   = status === "complete" || (status === "processing" && stageIdx > idx);
                  const isActive = status === "processing" && stageIdx === idx;

                  return (
                    <div key={stg.label} className="flex items-start gap-3 text-xs">
                      <div className="mt-0.5 shrink-0">
                        {isDone ? (
                          <div className="w-4 h-4 rounded-full bg-emerald-500 text-white grid place-items-center">
                            <CheckCircle2 className="w-3 h-3" />
                          </div>
                        ) : isActive ? (
                          <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-muted-foreground/30 text-muted-foreground text-[10px] grid place-items-center">
                            {idx + 1}
                          </div>
                        )}
                      </div>
                      <div>
                        <p className={`font-medium ${isDone ? "text-foreground" : isActive ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                          {stg.label}
                        </p>
                        <p className="text-[11px] text-muted-foreground leading-tight mt-0.5">{stg.sub}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Panel>

            {/* Extraction Summary Metric Card */}
            {status === "complete" && result && (
              <Panel className="p-5 bg-gradient-to-br from-emerald-500/5 to-blue-500/5 border-emerald-500/20 space-y-3">
                <h3 className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                  Extraction Summary
                </h3>
                <div className="grid grid-cols-2 gap-3 text-center">
                  <div className="p-2.5 rounded-lg bg-background/80 border">
                    <div className="text-lg font-bold text-foreground">{result.data?.length || 0}</div>
                    <div className="text-[11px] text-muted-foreground">Pages Processed</div>
                  </div>
                  <div className="p-2.5 rounded-lg bg-background/80 border">
                    <div className="text-lg font-bold text-emerald-600">{(result.data?.length || 0) * FIELD_KEYS.length}</div>
                    <div className="text-[11px] text-muted-foreground">Fields Extracted</div>
                  </div>
                </div>
              </Panel>
            )}

            {/* Error Display */}
            {status === "error" && error && (
              <Panel className="p-4 border-red-500/30 bg-red-500/5 flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <div className="text-xs text-red-600 dark:text-red-400">
                  <p className="font-semibold">Extraction Failed</p>
                  <p className="mt-0.5">{error}</p>
                </div>
              </Panel>
            )}
          </div>

          {/* ── RIGHT COLUMN: Extracted Results Table & Actions ──────────────── */}
          <div className="lg:col-span-7 space-y-5">
            {!result ? (
              <Panel className="p-12 text-center flex flex-col items-center justify-center min-h-[420px] border-dashed">
                <div className="w-16 h-16 rounded-full bg-muted grid place-items-center mb-4 text-muted-foreground">
                  <FileText className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold">No Extraction Results Yet</h3>
                <p className="text-xs text-muted-foreground max-w-sm mt-1">
                  Upload an Unemployment Claim PDF file on the left panel and click <strong>Run Extraction</strong> to view extracted fields here.
                </p>
              </Panel>
            ) : (
              <Panel className="p-5 space-y-4">
                {/* Header Actions & Downloads */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
                  <div>
                    <h3 className="text-sm font-semibold flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      Extraction Results
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {result.data?.length || 0} Page(s) • {(result.data?.length || 0) * FIELD_KEYS.length} Fields Extracted
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* 🟢 Download Excel Button */}
                    <Button size="sm" onClick={downloadExcel} className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs h-8">
                      <FileSpreadsheet className="w-3.5 h-3.5" /> Download Excel
                    </Button>

                    {/* 🔵 Download JSON Button */}
                    <Button size="sm" onClick={downloadJson} className="gap-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs h-8">
                      <FileJson className="w-3.5 h-3.5" /> Download JSON
                    </Button>
                  </div>
                </div>

                {/* Tabs & Page Selector */}
                <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)} className="w-full">
                  <div className="flex items-center justify-between border-b pb-2">
                    <TabsList className="h-8">
                      <TabsTrigger value="table" className="gap-1.5 text-xs h-7">
                        <Table2 className="w-3.5 h-3.5" /> Field Table
                      </TabsTrigger>
                      <TabsTrigger value="json" className="gap-1.5 text-xs h-7">
                        <FileJson className="w-3.5 h-3.5" /> Raw JSON
                      </TabsTrigger>
                    </TabsList>

                    {/* Multi-page selector buttons */}
                    {result.data && result.data.length > 1 && (
                      <div className="flex items-center gap-1 text-xs">
                        <span className="text-muted-foreground text-[11px] font-medium mr-1">Page:</span>
                        {result.data.map((_, idx) => (
                          <Button
                            key={idx}
                            size="sm"
                            variant={selectedPage === idx ? "default" : "outline"}
                            onClick={() => setSelectedPage(idx)}
                            className="h-6 px-2 text-[11px]"
                          >
                            {idx + 1}
                          </Button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* ── TAB 1: Extracted Fields Table matching PSH-UI Claim Validator layout ──── */}
                  <TabsContent value="table" className="mt-4">
                    <div className="border rounded-lg overflow-hidden">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-muted/50 border-b font-medium text-muted-foreground">
                          <tr>
                            <th className="py-2.5 px-4 w-1/2">FIELD</th>
                            <th className="py-2.5 px-4 w-1/2">EXTRACTED VALUE</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {FIELD_KEYS.map((key) => {
                            const meta = FIELD_META[key] || { label: key, icon: FileText };
                            const Icon = meta.icon;
                            const pageData = result.data?.[selectedPage] || {};
                            const val = pageData[key];

                            return (
                              <tr key={key} className="hover:bg-muted/20 transition-colors">
                                <td className="py-2.5 px-4 font-medium text-foreground flex items-center gap-2">
                                  <Icon className="w-3.5 h-3.5 text-primary shrink-0" />
                                  <span>{meta.label}</span>
                                </td>
                                <td className="py-2.5 px-4">
                                  {val !== undefined && val !== null && val !== "" ? (
                                    <span className="font-medium text-foreground break-all">{val}</span>
                                  ) : (
                                    <span className="text-muted-foreground/40 italic font-normal text-[11px]">—</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </TabsContent>

                  {/* ── TAB 2: Raw JSON View ─────────────────────────────────── */}
                  <TabsContent value="json" className="mt-4">
                    <div className="relative border rounded-lg p-3 bg-muted/30">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[11px] font-mono text-muted-foreground">Extracted JSON Data</span>
                        <Button size="sm" variant="ghost" onClick={copyJson} className="h-6 gap-1 text-[11px]">
                          <Copy className="w-3 h-3" /> Copy JSON
                        </Button>
                      </div>
                      <pre className="text-xs font-mono bg-background p-3 rounded border overflow-x-auto max-h-[400px] text-foreground">
                        {JSON.stringify(result.data, null, 2)}
                      </pre>
                    </div>
                  </TabsContent>
                </Tabs>
              </Panel>
            )}
          </div>

        </div>
      </div>
    </>
  );
}
