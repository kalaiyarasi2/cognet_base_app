import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useCallback } from "react";
import {
  ClipboardCheck, UploadCloud, FileImage, Loader2, Download,
  CheckCircle2, AlertCircle, FileJson, Table2, X, Copy,
  FileText, ScanLine, Calendar, Hash, Percent, DollarSign,
  MapPin, ShieldAlert, ChevronDown, ChevronUp
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";

export const Route = createFileRoute("/psh-claim-validator")({
  component: PshClaimValidatorPage,
});

// ─── Base-claim- app is mounted at /claim on the main backend (port 8000) ─────
const PSH_BACKEND_URL = "";
const PSH_CLAIM_PREFIX = "/claim";

// ─── Field metadata matching EXPECTED_KEYS in base-claim- backend ─────────────
const FIELD_META: Record<string, { label: string; icon: any }> = {
  claim_sui_account_number: { label: "SUI Account Number", icon: Hash },
  claimant_ssn: { label: "Claimant SSN", icon: ShieldAlert },
  claimant_name: { label: "Claimant Name", icon: FileText },
  claim_start_date: { label: "Claim Start Date", icon: Calendar },
  claim_end_date: { label: "Claim End Date", icon: Calendar },
  byb_date: { label: "BYB Date", icon: Calendar },
  bye_date: { label: "BYE Date", icon: Calendar },
  claim_mailing_date: { label: "Mailing Date", icon: Calendar },
  claim_liability_percentage: { label: "Liability %", icon: Percent },
  claim_liability_base_amount: { label: "Liability Base Amount", icon: DollarSign },
  agency_address_line_1: { label: "Agency Address Line 1", icon: MapPin },
  agency_address_line_2: { label: "Agency Address Line 2", icon: MapPin },
  separation_code: { label: "Separation Code", icon: ScanLine },
  calculated_claim_liability: { label: "Calculated Claim Liability", icon: DollarSign },
};

const FIELD_KEYS = Object.keys(FIELD_META);

// ─── Processing stages ────────────────────────────────────────────────────────
const STAGES = [
  { label: "Image Verified", sub: "Format validated successfully." },
  { label: "GPT Vision Running", sub: "Analyzing dual-panel screenshot..." },
  { label: "Generating Report", sub: "Building Excel & JSON outputs..." },
  { label: "Complete", sub: "Extraction finished successfully." },
];

type Status = "idle" | "processing" | "complete" | "error";

interface ExtractionResult {
  pdf: Record<string, string>;
  ocr: Record<string, string>;
  validation: Record<string, "Match" | "Mismatch">;
  token_usage: Record<string, any>;
  excel_download_url?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmtSize = (b: number) =>
  b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1048576).toFixed(1)} MB`;

// ─── Main Component ───────────────────────────────────────────────────────────
function PshClaimValidatorPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [stageIdx, setStageIdx] = useState(0);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"table" | "json">("table");
  const [isDragging, setIsDragging] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── File handlers ─────────────────────────────────────────────────────────
  const handleFile = (f: File) => {
    if (!f.type.startsWith("image/")) {
      toast.error("Only image files (.png, .jpg, .jpeg) are supported.");
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setStatus("idle");
    setResult(null);
    setError(null);
    setStageIdx(0);
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

  const clearAll = () => {
    setFile(null); setPreview(null);
    setStatus("idle"); setResult(null);
    setError(null); setStageIdx(0);
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
      const res = await fetch(`${PSH_BACKEND_URL}${PSH_CLAIM_PREFIX}/api/extract-screenshot`, {
        method: "POST",
        body: formData,
      });
      setStageIdx(2);

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Extraction failed");
      }

      const data: ExtractionResult = await res.json();
      setStageIdx(3);
      setResult(data);
      setStatus("complete");

      const matches = Object.values(data.validation).filter(v => v === "Match").length;
      toast.success(`Extraction complete — ${matches}/${FIELD_KEYS.length} fields matched`);
    } catch (err: any) {
      setError(err.message || "Unknown error");
      setStatus("error");
      toast.error("Extraction failed: " + (err.message || "Unknown error"));
    }
  };

  // ── Download ──────────────────────────────────────────────────────────────
  const downloadExcel = () => {
    if (!result?.excel_download_url) return;
    // excel_download_url from backend is like /api/download-excel/{name}
    // prepend the /claim mount prefix so it resolves correctly
    window.open(`${PSH_BACKEND_URL}${PSH_CLAIM_PREFIX}${result.excel_download_url}`, "_blank");
  };

  const copyJson = () => {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    toast.success("JSON copied to clipboard!");
  };

  // ── Computed stats ────────────────────────────────────────────────────────
  const matchCount = result ? Object.values(result.validation).filter(v => v === "Match").length : 0;
  const mismatchCount = result ? Object.values(result.validation).filter(v => v === "Mismatch").length : 0;
  const matchPct = result ? Math.round((matchCount / FIELD_KEYS.length) * 100) : 0;

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <>
      <PageHeader
        icon={ClipboardCheck}
        title="PSH-UI Claim Validator"
        description="Upload a dual-panel claim screenshot. GPT Vision extracts PDF & OCR fields and validates them field-by-field."
        actions={
          result ? (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={copyJson} className="gap-1.5">
                <Copy className="w-3.5 h-3.5" /> Copy JSON
              </Button>
              <Button size="sm" onClick={downloadExcel} className="gap-1.5">
                <Download className="w-3.5 h-3.5" /> Download Excel
              </Button>
            </div>
          ) : null
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

        {/* ══════════════ LEFT COLUMN ══════════════ */}
        <div className="xl:col-span-1 flex flex-col gap-4">

          {/* Upload Panel */}
          <Panel title="Upload Screenshot" description="Dual-panel claim image (PDF left · UI right)">
            {/* Drop Zone */}
            <div
              className={`
                relative rounded-xl border-2 border-dashed transition-all duration-200
                flex flex-col items-center justify-center text-center min-h-[160px] p-5 cursor-pointer
                ${isDragging
                  ? "border-primary bg-primary/5 scale-[1.01] shadow-md"
                  : file
                    ? "border-success/50 bg-success/5"
                    : "border-border hover:border-primary/40 hover:bg-muted/20"}
              `}
              onClick={() => !file && fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                className="hidden"
                onChange={onInputChange}
              />
              {file ? (
                <div className="flex items-center gap-3 w-full">
                  <div className="w-10 h-10 rounded-lg bg-success/10 flex items-center justify-center shrink-0">
                    <FileImage className="w-5 h-5 text-success" />
                  </div>
                  <div className="flex-1 min-w-0 text-left">
                    <p className="text-sm font-medium truncate">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{fmtSize(file.size)}</p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); clearAll(); }}
                    className="w-6 h-6 rounded-full bg-muted hover:bg-destructive/10 hover:text-destructive flex items-center justify-center transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <>
                  <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mb-3">
                    <UploadCloud className="w-6 h-6 text-primary" />
                  </div>
                  <p className="text-sm font-medium">Drop screenshot here</p>
                  <p className="text-xs text-muted-foreground mt-1">PNG, JPG or JPEG</p>
                </>
              )}
            </div>

            {/* Image Preview (collapsible) */}
            {preview && (
              <div className="mt-3">
                <button
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2"
                  onClick={() => setShowPreview(v => !v)}
                >
                  {showPreview ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  {showPreview ? "Hide" : "Show"} Preview
                </button>
                {showPreview && (
                  <img
                    src={preview}
                    alt="Screenshot preview"
                    className="w-full rounded-lg border border-border object-contain max-h-52 shadow-sm"
                  />
                )}
              </div>
            )}

            {/* Run button */}
            <Button
              className="w-full mt-4 gap-2"
              disabled={!file || status === "processing"}
              onClick={runExtraction}
            >
              {status === "processing" ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Extracting...</>
              ) : (
                <><ClipboardCheck className="w-4 h-4" /> Run Extraction</>
              )}
            </Button>

            {/* Backend info badge */}
            <p className="text-center text-[10px] text-muted-foreground mt-2">
              Connected to <code className="font-mono bg-muted px-1 rounded">{PSH_BACKEND_URL}{PSH_CLAIM_PREFIX}</code>
            </p>
          </Panel>

          {/* Status Stepper */}
          {status !== "idle" && (
            <Panel title="Extraction Progress" description="Real-time stage tracking">
              <ol className="space-y-0">
                {STAGES.map((stage, i) => {
                  const done = status === "complete" || i < stageIdx;
                  const active = status === "processing" && i === stageIdx;
                  const errored = status === "error" && i === stageIdx;
                  return (
                    <li key={i} className="flex gap-3 pb-4 last:pb-0 relative">
                      {i < STAGES.length - 1 && (
                        <div className={`absolute left-3.5 top-7 w-px h-full ${done ? "bg-primary/50" : "bg-border"}`} />
                      )}
                      <div className={`
                        w-7 h-7 rounded-full flex items-center justify-center shrink-0 z-10 text-xs font-bold transition-all
                        ${errored ? "bg-destructive text-destructive-foreground"
                          : done ? "bg-primary text-primary-foreground"
                            : active ? "bg-primary/15 text-primary ring-2 ring-primary/30"
                              : "bg-muted text-muted-foreground/60"}
                      `}>
                        {errored ? <AlertCircle className="w-3.5 h-3.5" />
                          : done ? <CheckCircle2 className="w-3.5 h-3.5" />
                            : active ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : i + 1}
                      </div>
                      <div className="pt-0.5 min-w-0">
                        <p className={`text-[13px] font-medium leading-tight ${active ? "text-primary" : done ? "text-foreground" : "text-muted-foreground/60"}`}>
                          {stage.label}
                        </p>
                        {(active || done || errored) && (
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            {errored ? (error || "Error occurred") : stage.sub}
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>

              {status === "error" && (
                <div className="mt-3 p-3 rounded-lg bg-destructive/8 border border-destructive/20 flex gap-2">
                  <AlertCircle className="w-4 h-4 text-destructive shrink-0 mt-0.5" />
                  <p className="text-xs text-destructive break-all">{error}</p>
                </div>
              )}
            </Panel>
          )}

          {/* Validation Summary */}
          {result && (
            <Panel title="Validation Summary" description="Match rate across all 13 fields">
              {/* Progress bar */}
              <div className="mb-4">
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-muted-foreground">Match Rate</span>
                  <span className="font-bold text-foreground">{matchPct}%</span>
                </div>
                <div className="h-2.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${matchPct === 100 ? "bg-success" : matchPct >= 70 ? "bg-primary" : "bg-warning"}`}
                    style={{ width: `${matchPct}%` }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="bg-success/10 border border-success/20 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-success">{matchCount}</p>
                  <p className="text-[10px] font-semibold text-success/80 uppercase tracking-wide mt-0.5">Matched</p>
                </div>
                <div className="bg-destructive/8 border border-destructive/15 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-destructive">{mismatchCount}</p>
                  <p className="text-[10px] font-semibold text-destructive/80 uppercase tracking-wide mt-0.5">Mismatched</p>
                </div>
              </div>

              {/* Token cost */}
              {result.token_usage && Object.keys(result.token_usage).length > 0 && (
                <div className="mt-3 pt-3 border-t border-border grid grid-cols-2 gap-2">
                  {[
                    { k: "prompt_tokens", label: "Prompt Tokens" },
                    { k: "completion_tokens", label: "Output Tokens" },
                    { k: "total_tokens", label: "Total Tokens" },
                    { k: "estimated_cost_usd", label: "Est. Cost" },
                  ].map(({ k, label }) => {
                    const val = result.token_usage[k];
                    const display = k === "estimated_cost_usd" && val != null
                      ? `$${Number(val).toFixed(6)}`
                      : val ?? "—";
                    return (
                      <div key={k} className="bg-muted/40 rounded-lg px-3 py-2">
                        <p className="text-[10px] text-muted-foreground font-medium">{label}</p>
                        <p className="text-sm font-bold">{display}</p>
                      </div>
                    );
                  })}
                </div>
              )}
            </Panel>
          )}
        </div>

        {/* ══════════════ RIGHT COLUMN ══════════════ */}
        <div className="xl:col-span-2">

          {/* Empty state */}
          {!result && status !== "processing" && (
            <Panel title="Extracted Data" description="Results appear here after extraction">
              <div className="h-80 flex flex-col items-center justify-center gap-4 text-muted-foreground">
                <div className="w-20 h-20 rounded-3xl bg-muted/60 flex items-center justify-center">
                  <ClipboardCheck className="w-10 h-10 opacity-20" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">No data yet</p>
                  <p className="text-xs mt-1">Upload a dual-panel screenshot and click Run Extraction</p>
                </div>
              </div>
            </Panel>
          )}

          {/* Loading state */}
          {status === "processing" && (
            <Panel title="Extracting..." description="GPT Vision is analyzing your screenshot">
              <div className="h-80 flex flex-col items-center justify-center gap-5">
                <div className="relative">
                  <div className="w-20 h-20 rounded-full border-4 border-primary/15 border-t-primary animate-spin" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <ClipboardCheck className="w-7 h-7 text-primary" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-sm font-semibold">Dual-Panel Analysis</p>
                  <p className="text-xs text-muted-foreground mt-1 animate-pulse">
                    Comparing PDF Notice vs UI Entry Screen...
                  </p>
                </div>
              </div>
            </Panel>
          )}

          {/* Results */}
          {result && (
            <Panel
              title="Extraction Results"
              description={`${FIELD_KEYS.length} fields · ${matchCount} matched · ${mismatchCount} mismatched`}
            >
              {/* View toggle */}
              <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
                <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)}>
                  <TabsList className="h-8">
                    <TabsTrigger value="table" className="gap-1.5 text-xs h-7 px-3">
                      <Table2 className="w-3.5 h-3.5" /> Comparison
                    </TabsTrigger>
                    <TabsTrigger value="json" className="gap-1.5 text-xs h-7 px-3">
                      <FileJson className="w-3.5 h-3.5" /> Raw JSON
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
                <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={downloadExcel}>
                  <Download className="w-3.5 h-3.5" /> Excel Report
                </Button>
              </div>

              {/* ── TABLE VIEW: PDF vs OCR comparison ── */}
              {viewMode === "table" && (
                <div className="rounded-xl border border-border overflow-hidden">
                  {/* Column headers */}
                  <div className="grid grid-cols-[1fr_1fr_1fr_80px] bg-muted/50 border-b border-border text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    <div className="px-4 py-2.5">Field</div>
                    <div className="px-4 py-2.5 border-l border-border flex items-center gap-1.5">
                      <FileText className="w-3 h-3" /> PDF (Notice)
                    </div>
                    <div className="px-4 py-2.5 border-l border-border flex items-center gap-1.5">
                      <ScanLine className="w-3 h-3" /> OCR (Entry Screen)
                    </div>
                    <div className="px-4 py-2.5 border-l border-border text-center">Status</div>
                  </div>

                  {/* Rows */}
                  {FIELD_KEYS.map((key, idx) => {
                    const meta = FIELD_META[key];
                    const pdfVal = result.pdf[key] || "—";
                    const ocrVal = result.ocr[key] || "—";
                    const isMatch = result.validation[key] === "Match";
                    const Icon = meta?.icon ?? FileText;

                    return (
                      <div
                        key={key}
                        className={`grid grid-cols-[1fr_1fr_1fr_80px] border-b last:border-b-0 border-border text-sm transition-colors
                          ${idx % 2 === 0 ? "bg-background" : "bg-muted/20"}
                          ${!isMatch ? "bg-destructive/4" : ""}
                        `}
                      >
                        {/* Field name */}
                        <div className="px-4 py-3 flex items-center gap-2 min-w-0">
                          <Icon className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                          <span className="text-[12px] font-medium text-foreground/80 truncate">
                            {meta?.label ?? key}
                          </span>
                        </div>

                        {/* PDF value */}
                        <div className="px-4 py-3 border-l border-border/50 flex items-center min-w-0">
                          <span className={`text-[12.5px] truncate ${pdfVal === "—" ? "text-muted-foreground/40 italic" : "text-foreground"}`}>
                            {pdfVal}
                          </span>
                        </div>

                        {/* OCR value */}
                        <div className="px-4 py-3 border-l border-border/50 flex items-center min-w-0">
                          <span className={`text-[12.5px] truncate ${ocrVal === "—" ? "text-muted-foreground/40 italic" : "text-foreground"}`}>
                            {ocrVal}
                          </span>
                        </div>

                        {/* Match/Mismatch badge */}
                        <div className="px-3 py-3 border-l border-border/50 flex items-center justify-center">
                          {isMatch ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-success/15 text-success border border-success/25">
                              <CheckCircle2 className="w-2.5 h-2.5" /> Match
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-destructive/12 text-destructive border border-destructive/20">
                              <AlertCircle className="w-2.5 h-2.5" /> Diff
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* ── JSON VIEW ── */}
              {viewMode === "json" && (
                <div className="relative rounded-xl border border-border bg-muted/30 overflow-auto max-h-[600px]">
                  <div className="absolute top-3 right-3 z-10">
                    <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={copyJson}>
                      <Copy className="w-3 h-3" /> Copy
                    </Button>
                  </div>
                  <pre className="p-5 text-[11.5px] font-mono leading-relaxed text-foreground whitespace-pre-wrap">
                    {JSON.stringify({ pdf: result.pdf, ocr: result.ocr, validation: result.validation }, null, 2)}
                  </pre>
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
