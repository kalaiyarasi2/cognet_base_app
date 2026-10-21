import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect, useMemo } from "react";
import {
  FileSpreadsheet,
  UploadCloud,
  FileText,
  Loader2,
  Download,
  Copy,
  Check,
  Play,
  FolderOpen,
  CheckCircle2,
  Eye,
  X,
  Mail,
  RefreshCw,
  Briefcase,
  RotateCcw,
  Calendar,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { api, getBackendUrl, type BenefitsUwPipelineResponse } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/benefits-uw")({
  component: BenefitsUWPage,
});

interface StagedFile {
  id: string;
  file: File;
  name: string;
  size: string;
  roleHint: string;
}

const RECORD_TYPE_OPTIONS = [
  "PEO",
  "ASO",
  "Client Growth",
  "Payroll Only",
  "Retention",
  "Retirement Planning",
  "WC only",
];

const STAGE_OPTIONS = [
  "First Meeting",
  "Discovery",
  "Qualification",
  "Proposal / Quote",
  "Underwriting",
  "Closed Won",
  "Closed Lost",
];

const GENERATED_BY_OPTIONS = [
  "Channel Partner",
  "Direct / Self-Generated",
  "Client Referral",
  "Internal Sales",
];

const PIPELINE_STEPS = [
  "Reading & Classifying Documents",
  "Census & Dependents Consolidation",
  "Invoice Subscriber Matching & Reconciliation",
  "Applying Underwriting Rules & Renewal Rates",
  "Generating Master Workbook & Exceptions",
];

function getDownloadUrl(path: string | null | undefined): string {
  if (!path) return "#";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const base = getBackendUrl();
  const clean = path.startsWith("/") ? path : `/${path}`;
  if (clean.startsWith("/api/benefits-uw/")) {
    return `${base}${clean}`;
  }
  return `${base}/api/benefits-uw${clean}`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateMMDDYYYY(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const yyyy = d.getFullYear();
  return `${mm}/${dd}/${yyyy}`;
}

function getInitialOpportunityState() {
  const now = new Date();
  const plus60 = new Date(now.getTime() + 60 * 24 * 60 * 60 * 1000);
  return {
    recordType: "PEO",
    opportunityName: "", // Cleared initial hardcoded name; auto-populates from submission files or detected prospect
    stage: "First Meeting",
    firstMeetingDate: formatDateMMDDYYYY(now),
    generatedBy: "Channel Partner",
    channelPartner: "TBD",
    closeDate: formatDateMMDDYYYY(plus60),
    estFirstPayrollDate: formatDateMMDDYYYY(plus60),
  };
}

function detectRoleHint(name: string): string {
  const lower = name.toLowerCase();
  if (lower.includes("census")) return "CENSUS";
  if (lower.includes("invoice") || lower.includes("bill")) return "INVOICE";
  if (lower.includes("renewal") || lower.includes("rate")) return "RENEWAL";
  if (lower.includes("ghq") || lower.includes("rfp")) return "GHQ / RFP";
  if (lower.endsWith(".docx")) return "DOC";
  return "DOCUMENT";
}

function extractProspectFromFilename(filename: string): string {
  if (!filename) return "";
  let clean = filename.replace(/^(RAPT|Marsh|SBU)_Census_/i, "");
  clean = clean.replace(/_\d{8}_\d{6}\.xlsx$/i, "");
  clean = clean.replace(/_/g, " ").trim();
  return clean;
}

function extractProspectFromStagedFiles(files: StagedFile[]): string {
  if (!files || files.length === 0) return "";
  for (const sf of files) {
    const clean = sf.name.replace(/\.(pdf|xlsx|xls|docx|csv)$/i, "");
    const match = clean.match(/^([A-Za-z0-9&',.\s]+?)(?:_|\s+)(?:Admin|Invoice|Benefit|Contribution|Census|Report|Current|Renewal|GHQ|RFP)/i);
    if (match && match[1].trim().length > 2) {
      let prospect = match[1].trim().replace(/^RAPT_Census_/i, "").replace(/^Marsh_Census_/i, "").replace(/_/g, " ");
      return prospect;
    }
  }
  return "";
}

function parseAuditMetrics(result: BenefitsUwPipelineResponse | null) {
  if (!result) {
    return {
      employees: 0,
      srcEmployees: 0,
      dependents: 0,
      srcDependents: 0,
      missingInvoice: 0,
      missingCensus: 0,
      tierMismatches: 0,
      duplicateEmployees: 0,
    };
  }

  let outEmp = result.audit?.out_employees ?? result.audit?.output_employees ?? 0;
  let srcEmp = result.audit?.src_employees ?? result.audit?.source_employees ?? 0;
  let outDep = result.audit?.out_dependents ?? result.audit?.output_dependents ?? 0;
  let srcDep = result.audit?.src_dependents ?? result.audit?.source_dependents ?? 0;
  let missingInv = result.counters?.missing_invoice ?? 0;
  let missingCensus = result.counters?.missing_census ?? 0;
  let tierMismatches = result.counters?.tier_mismatch ?? result.counters?.tier_mismatches ?? 0;
  let duplicates = result.counters?.duplicate_employees ?? result.audit?.duplicate_employees ?? 0;

  // Fallback / verification from exception summary text
  const summary = result.summary || "";
  if (summary) {
    const censusMatch = summary.match(/Census:\s*(\d+)\s*employees\s*\/\s*(\d+)\s*dependents/i);
    if (censusMatch) {
      const parsedEmp = parseInt(censusMatch[1], 10);
      const parsedDep = parseInt(censusMatch[2], 10);
      if (!outEmp) outEmp = parsedEmp;
      if (!srcEmp) srcEmp = parsedEmp;
      if (!outDep) outDep = parsedDep;
      if (!srcDep) srcDep = parsedDep;
    }
    const missingInvMatch = summary.match(/Missing from invoice:\s*(\d+)/i);
    if (missingInvMatch && missingInv === 0) {
      missingInv = parseInt(missingInvMatch[1], 10);
    }
    const missingCensusMatch = summary.match(/Missing from census:\s*(\d+)/i);
    if (missingCensusMatch && missingCensus === 0) {
      missingCensus = parseInt(missingCensusMatch[1], 10);
    }
    const tierMatch = summary.match(/Tier mismatches:\s*(\d+)/i);
    if (tierMatch && tierMismatches === 0) {
      tierMismatches = parseInt(tierMatch[1], 10);
    }
    const dupMatch = summary.match(/Duplicate employees:\s*(\d+)/i);
    if (dupMatch && duplicates === 0) {
      duplicates = parseInt(dupMatch[1], 10);
    }
  }

  return {
    employees: outEmp,
    srcEmployees: srcEmp || outEmp,
    dependents: outDep,
    srcDependents: srcDep || outDep,
    missingInvoice: missingInv,
    missingCensus: missingCensus,
    tierMismatches: tierMismatches,
    duplicateEmployees: duplicates,
  };
}

function BenefitsUWPage() {
  const [ingestMode, setIngestMode] = useState<"upload" | "folder">("upload");
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [folderPath, setFolderPath] = useState<string>("input");
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [activeStep, setActiveStep] = useState<number>(0);
  const [result, setResult] = useState<BenefitsUwPipelineResponse | null>(null);

  // Opportunity & Submission Setup Fields State
  const [oppState, setOppState] = useState(getInitialOpportunityState);

  // Extracted text modal state
  const [modalOpen, setModalOpen] = useState<boolean>(false);
  const [modalTitle, setModalTitle] = useState<string>("");
  const [modalText, setModalText] = useState<string>("");
  const [modalCharCount, setModalCharCount] = useState<number>(0);
  const [modalLoading, setModalLoading] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Detected prospect name from pipeline result or staged files
  const detectedProspectName = useMemo(() => {
    if (result) {
      return (
        result.prospect_name ||
        result.company ||
        extractProspectFromFilename(result.output_filename) ||
        ""
      );
    }
    return extractProspectFromStagedFiles(stagedFiles);
  }, [result, stagedFiles]);

  // Auto-populate Opportunity Name when pipeline results finish
  useEffect(() => {
    if (result) {
      const detected =
        result.prospect_name ||
        result.company ||
        extractProspectFromFilename(result.output_filename) ||
        extractProspectFromStagedFiles(stagedFiles);
      if (detected) {
        setOppState((prev) => ({
          ...prev,
          opportunityName: detected,
        }));
      }
    }
  }, [result, stagedFiles]);

  const metrics = useMemo(() => parseAuditMetrics(result), [result]);

  const handleResetDefaults = () => {
    setOppState(getInitialOpportunityState());
    toast.success("Opportunity & Submission parameters reset to defaults.");
  };

  const handleCopyOpportunityDetails = () => {
    const text = `OPPORTUNITY & SUBMISSION SETUP
Record Type: ${oppState.recordType}
Opportunity Name: ${oppState.opportunityName}
Stage: ${oppState.stage}
First Meeting Date: ${oppState.firstMeetingDate}
Opportunity Generated By: ${oppState.generatedBy}
Channel Partner: ${oppState.channelPartner}
Close Date: ${oppState.closeDate}
Est. First Payroll Date: ${oppState.estFirstPayrollDate}`;

    navigator.clipboard.writeText(text);
    toast.success("Opportunity details copied to clipboard!");
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const added: StagedFile[] = Array.from(files).map((f) => ({
      id: Math.random().toString(36).substring(2, 9),
      file: f,
      name: f.name,
      size: formatBytes(f.size),
      roleHint: detectRoleHint(f.name),
    }));
    setStagedFiles((prev) => {
      const allFiles = [...prev, ...added];
      const autoProspect = extractProspectFromStagedFiles(allFiles);
      if (autoProspect && !oppState.opportunityName) {
        setOppState((os) => ({ ...os, opportunityName: autoProspect }));
      }
      return allFiles;
    });
    toast.success(`Added ${added.length} file(s) for ingestion`);
  };

  const removeFile = (id: string) => {
    setStagedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const clearAllFiles = () => {
    setStagedFiles([]);
  };

  const triggerStepAnimation = () => {
    setActiveStep(0);
    const interval = setInterval(() => {
      setActiveStep((prev) => {
        if (prev < PIPELINE_STEPS.length - 1) {
          return prev + 1;
        }
        clearInterval(interval);
        return prev;
      });
    }, 900);
    return () => clearInterval(interval);
  };

  // Run upload-based processing
  const handleProcessFiles = async () => {
    if (stagedFiles.length === 0) {
      toast.error("Please add submission files to process.");
      return;
    }

    setIsProcessing(true);
    setResult(null);
    const stopAnim = triggerStepAnimation();

    try {
      const fd = new FormData();
      stagedFiles.forEach((f) => {
        fd.append("files", f.file);
      });

      const res = await api.benefitsUwProcess(fd);
      setResult(res);
      toast.success("BenefitsUW census comparison pipeline completed successfully!");
    } catch (err: any) {
      console.error("BenefitsUW process error:", err);
      toast.error(`Pipeline failed: ${err.message || err}`);
    } finally {
      stopAnim();
      setIsProcessing(false);
    }
  };

  // Run folder-based processing
  const handleProcessFolder = async () => {
    if (!folderPath.trim()) {
      toast.error("Please provide a valid directory path.");
      return;
    }

    setIsProcessing(true);
    setResult(null);
    const stopAnim = triggerStepAnimation();

    try {
      const res = await api.benefitsUwTestFolder(folderPath.trim());
      setResult(res);
      toast.success("Folder pipeline completed successfully!");
    } catch (err: any) {
      console.error("BenefitsUW folder error:", err);
      toast.error(`Folder pipeline failed: ${err.message || err}`);
    } finally {
      stopAnim();
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text: string, label: string = "Text") => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard!`);
  };

  const viewExtractedText = async (filename: string) => {
    setModalTitle(filename);
    setModalOpen(true);
    setModalLoading(true);
    setModalText("");
    setModalCharCount(0);

    try {
      const data = await api.benefitsUwGetExtractedText(filename);
      setModalText(data.content || "No extracted text found.");
      setModalCharCount(data.content?.length || 0);
    } catch (err: any) {
      setModalText(`Error loading extracted text: ${err.message || err}`);
    } finally {
      setModalLoading(false);
    }
  };


  return (
    <div className="space-y-6 pb-12">
      {/* Header Banner - BenefitsUW */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 rounded-xl border border-border/60 bg-gradient-to-r from-card/90 via-card to-card/60 backdrop-blur-sm shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/20 shadow-inner shrink-0">
            <FileSpreadsheet className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-foreground">
                BenefitsUW
              </h1>
              <Badge variant="outline" className="text-[10px] font-mono tracking-wider bg-primary/5 text-primary border-primary/20">
                BENEFITS-UW
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Health Insurance Census Creation & Multi-Document Reconciliation
            </p>
          </div>
        </div>
      </div>

      {/* Main 2-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Document Ingestion */}
        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-xl border border-border bg-card p-5 shadow-xs space-y-4">
            <div className="flex items-start gap-3">
              <div className="w-9 h-9 rounded-lg bg-primary/10 text-primary flex items-center justify-center shrink-0">
                <UploadCloud className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-foreground">Document Ingestion</h2>
                <p className="text-xs text-muted-foreground">
                  Upload employee census, invoices, renewals, and GHQ documents.
                </p>
              </div>
            </div>

            {/* Ingestion Mode Switcher */}
            <div className="grid grid-cols-2 p-1 bg-muted/60 rounded-lg text-xs font-medium border border-border/40">
              <button
                type="button"
                onClick={() => setIngestMode("upload")}
                className={`py-1.5 px-3 rounded-md transition-all text-center ${
                  ingestMode === "upload"
                    ? "bg-card text-foreground font-semibold shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Upload Files
              </button>
              <button
                type="button"
                onClick={() => setIngestMode("folder")}
                className={`py-1.5 px-3 rounded-md transition-all text-center ${
                  ingestMode === "folder"
                    ? "bg-card text-foreground font-semibold shadow-xs"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                Test Local Folder
              </button>
            </div>

            {/* Mode 1: Drag & Drop File Upload */}
            {ingestMode === "upload" && (
              <div className="space-y-3.5">
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    handleFiles(e.dataTransfer.files);
                  }}
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-border hover:border-primary/50 transition-colors rounded-xl p-6 text-center cursor-pointer bg-muted/20 hover:bg-muted/40 group"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".xlsx,.xlsm,.xls,.csv,.pdf,.docx,.txt"
                    className="hidden"
                    onChange={(e) => handleFiles(e.target.files)}
                  />
                  <div className="w-12 h-12 rounded-full bg-primary/10 text-primary mx-auto mb-3 flex items-center justify-center group-hover:scale-105 transition-transform">
                    <UploadCloud className="w-6 h-6" />
                  </div>
                  <p className="text-sm font-semibold text-foreground">
                    Drag & drop submission files here
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    or <span className="text-primary underline font-medium">browse files</span> from your computer
                  </p>
                  <div className="flex flex-wrap items-center justify-center gap-1.5 mt-3.5">
                    <span className="text-[10px] font-medium bg-muted px-2 py-0.5 rounded text-muted-foreground">
                      Excel (.xlsx, .xls)
                    </span>
                    <span className="text-[10px] font-medium bg-muted px-2 py-0.5 rounded text-muted-foreground">
                      PDF (Digital & Scanned)
                    </span>
                    <span className="text-[10px] font-medium bg-muted px-2 py-0.5 rounded text-muted-foreground">
                      Word (.docx)
                    </span>
                    <span className="text-[10px] font-medium bg-muted px-2 py-0.5 rounded text-muted-foreground">
                      CSV
                    </span>
                  </div>
                </div>

                {/* Staged files list */}
                {stagedFiles.length > 0 && (
                  <div className="rounded-lg border border-border/60 bg-muted/30 p-3 space-y-2">
                    <div className="flex items-center justify-between text-xs pb-1 border-b border-border/40">
                      <span className="font-semibold text-foreground">
                        {stagedFiles.length} file{stagedFiles.length > 1 ? "s" : ""} selected
                      </span>
                      <button
                        type="button"
                        onClick={clearAllFiles}
                        className="text-destructive hover:underline text-[11px] font-medium"
                      >
                        Clear All
                      </button>
                    </div>

                    <div className="max-h-52 overflow-y-auto space-y-1.5 pr-1">
                      {stagedFiles.map((sf) => (
                        <div
                          key={sf.id}
                          className="flex items-center justify-between gap-2 p-2 rounded-md bg-card border border-border/40 text-xs hover:border-border transition-colors"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText className="w-3.5 h-3.5 text-primary shrink-0" />
                            <span className="truncate font-medium text-foreground">{sf.name}</span>
                            <span className="text-[10px] text-muted-foreground shrink-0 font-mono">
                              {sf.size}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Badge
                              variant="secondary"
                              className="text-[9px] uppercase tracking-wider py-0 px-1.5 font-semibold bg-primary/10 text-primary border-primary/20"
                            >
                              {sf.roleHint}
                            </Badge>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                removeFile(sf.id);
                              }}
                              className="text-muted-foreground hover:text-destructive p-0.5 rounded transition-colors"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Process Button */}
                <Button
                  onClick={handleProcessFiles}
                  disabled={stagedFiles.length === 0 || isProcessing}
                  className="w-full gap-2 h-11 text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs"
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Processing Files...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-white" />
                      Process Files & Generate Census
                    </>
                  )}
                </Button>
              </div>
            )}

            {/* Mode 2: Test Local Folder */}
            {ingestMode === "folder" && (
              <div className="space-y-3.5">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Local Directory Path</label>
                  <input
                    type="text"
                    value={folderPath}
                    onChange={(e) => setFolderPath(e.target.value)}
                    placeholder="e.g. input or C:\path\to\folder"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-card text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-mono"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Specify a local folder path containing census, invoice, and renewal files.
                  </p>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground text-[11px]">Quick preset:</span>
                  <button
                    type="button"
                    onClick={() => setFolderPath("input")}
                    className="text-[11px] px-2 py-0.5 rounded border border-border bg-muted/60 hover:bg-muted text-foreground font-mono"
                  >
                    Default input/ Folder
                  </button>
                </div>

                <Button
                  onClick={handleProcessFolder}
                  disabled={!folderPath.trim() || isProcessing}
                  className="w-full gap-2 h-11 text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs"
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Running Folder Pipeline...
                    </>
                  ) : (
                    <>
                      <FolderOpen className="w-4 h-4" />
                      Run Pipeline on Folder
                    </>
                  )}
                </Button>
              </div>
            )}

            {/* Preserved Logic Notice */}
            <div className="p-3 rounded-lg border border-blue-500/20 bg-blue-500/5 text-xs text-muted-foreground flex items-start gap-2.5">
              <span className="text-base leading-none">💡</span>
              <p className="leading-relaxed">
                <strong className="text-foreground">REI Preserved Template Logic:</strong> Underwriting columns A–L remain untouched. Comparison section starts at column M.
              </p>
            </div>
          </div>
        </div>

        {/* Right Column: Opportunity & Submission Setup + Results */}
        <div className="lg:col-span-7 space-y-4">
          {/* Opportunity & Submission Setup Section - Spacious, un-congested 2-column grid */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                  <Briefcase className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold text-foreground">
                      Opportunity & Submission Setup
                    </h2>
                    <Badge variant="outline" className="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20 font-medium">
                      8 Intake Fields
                    </Badge>
                  </div>
                  <p className="text-[11.5px] text-muted-foreground mt-0.5">
                    Configure CRM opportunity parameters, intake classification & target payroll dates (MM/DD/YYYY)
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCopyOpportunityDetails}
                  className="h-8 text-xs gap-1.5"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Copy Details
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleResetDefaults}
                  className="h-8 text-xs gap-1.5 text-muted-foreground hover:text-foreground"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset to Defaults
                </Button>
              </div>
            </div>

            {/* 8 Opportunity Setup Fields Grid (2 spacious columns to eliminate congestion) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4 pt-1">
              {/* Field 1: Select Record Type */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Select Record Type</label>
                  <span className="text-[10.5px] text-muted-foreground">Default: PEO</span>
                </div>
                <select
                  value={oppState.recordType}
                  onChange={(e) => setOppState((prev) => ({ ...prev, recordType: e.target.value }))}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-medium"
                >
                  {RECORD_TYPE_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt === "PEO" ? "PEO (Default)" : opt}
                    </option>
                  ))}
                </select>
              </div>

              {/* Field 2: Opportunity Name (Prospect Name / Carrier) */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground flex items-center gap-1.5">
                    <span>Opportunity Name</span>
                    <span className="text-[10.5px] font-normal text-muted-foreground">
                      (Same as Prospect Name)
                    </span>
                  </label>
                  {result?.carrier && (
                    <Badge
                      variant="outline"
                      className="text-[10px] py-0 px-1.5 font-semibold text-purple-600 dark:text-purple-400 border-purple-500/30 bg-purple-500/10"
                    >
                      Carrier: {result.carrier}
                    </Badge>
                  )}
                </div>
                <input
                  type="text"
                  value={oppState.opportunityName}
                  onChange={(e) => setOppState((prev) => ({ ...prev, opportunityName: e.target.value }))}
                  placeholder={detectedProspectName ? detectedProspectName : "e.g. Civic Communications, LLC"}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-medium"
                />

                {/* Detected Prospect & Carrier Sync Actions */}
                <div className="flex flex-wrap items-center gap-2 pt-0.5">
                  {detectedProspectName && detectedProspectName !== oppState.opportunityName && (
                    <button
                      type="button"
                      onClick={() =>
                        setOppState((prev) => ({ ...prev, opportunityName: detectedProspectName }))
                      }
                      className="text-[10.5px] text-emerald-600 dark:text-emerald-400 hover:underline font-medium inline-flex items-center gap-1"
                    >
                      <Sparkles className="w-3 h-3" />
                      Set to Prospect: "{detectedProspectName}"
                    </button>
                  )}
                  {detectedProspectName && result?.carrier && (
                    <button
                      type="button"
                      onClick={() =>
                        setOppState((prev) => ({
                          ...prev,
                          opportunityName: `${detectedProspectName} - ${result.carrier}`,
                        }))
                      }
                      className="text-[10.5px] text-purple-600 dark:text-purple-400 hover:underline font-medium inline-flex items-center gap-1"
                    >
                      <span>+ Carrier: "{detectedProspectName} - {result.carrier}"</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Field 3: Stage */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Stage</label>
                  <span className="text-[10.5px] text-muted-foreground">Default: First Meeting</span>
                </div>
                <select
                  value={oppState.stage}
                  onChange={(e) => setOppState((prev) => ({ ...prev, stage: e.target.value }))}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-medium"
                >
                  {STAGE_OPTIONS.map((stg) => (
                    <option key={stg} value={stg}>
                      {stg}
                    </option>
                  ))}
                </select>
              </div>

              {/* Field 4: First Meeting Date */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">First Meeting Date</label>
                  <span className="text-[10.5px] text-muted-foreground font-mono">MM/DD/YYYY</span>
                </div>
                <div className="relative">
                  <input
                    type="text"
                    value={oppState.firstMeetingDate}
                    onChange={(e) => setOppState((prev) => ({ ...prev, firstMeetingDate: e.target.value }))}
                    className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-mono"
                  />
                  <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
              </div>

              {/* Field 5: Opportunity Generated By */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Opportunity Generated By</label>
                  <span className="text-[10.5px] text-muted-foreground">Default: Channel Partner</span>
                </div>
                <select
                  value={oppState.generatedBy}
                  onChange={(e) => setOppState((prev) => ({ ...prev, generatedBy: e.target.value }))}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-medium"
                >
                  {GENERATED_BY_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>

              {/* Field 6: Channel Partner */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Channel Partner</label>
                  <span className="text-[10.5px] text-muted-foreground">Broker Name</span>
                </div>
                <input
                  type="text"
                  value={oppState.channelPartner}
                  onChange={(e) => setOppState((prev) => ({ ...prev, channelPartner: e.target.value }))}
                  placeholder="TBD"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-medium"
                />
              </div>

              {/* Field 7: Close Date */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Close Date</label>
                  <span className="text-[10.5px] text-muted-foreground font-mono">+60 Days (MM/DD/YYYY)</span>
                </div>
                <div className="relative">
                  <input
                    type="text"
                    value={oppState.closeDate}
                    onChange={(e) => setOppState((prev) => ({ ...prev, closeDate: e.target.value }))}
                    className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-mono"
                  />
                  <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
              </div>

              {/* Field 8: Est. First Payroll Date */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <label className="font-semibold text-foreground">Est. First Payroll Date</label>
                  <span className="text-[10.5px] text-muted-foreground font-mono">+60 Days (MM/DD/YYYY)</span>
                </div>
                <div className="relative">
                  <input
                    type="text"
                    value={oppState.estFirstPayrollDate}
                    onChange={(e) => setOppState((prev) => ({ ...prev, estFirstPayrollDate: e.target.value }))}
                    className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary font-mono"
                  />
                  <Calendar className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
                </div>
              </div>
            </div>
          </div>

          {/* State 1: Idle Empty State */}
          {!result && !isProcessing && (
            <div className="rounded-xl border border-border bg-card p-10 text-center shadow-xs">
              <div className="w-16 h-16 rounded-2xl bg-muted mx-auto mb-4 flex items-center justify-center text-muted-foreground">
                <FileSpreadsheet className="w-8 h-8 stroke-[1.5]" />
              </div>
              <h3 className="text-base font-semibold text-foreground">
                Ready for File Reconciliation
              </h3>
              <p className="text-xs text-muted-foreground mt-1.5 max-w-md mx-auto leading-relaxed">
                Upload files or select a folder to begin. The pipeline will classify your documents, consolidate subscribers & dependents, reconcile billing against invoices, and populate future renewal rates.
              </p>

              <div className="grid grid-cols-2 gap-2.5 max-w-sm mx-auto mt-6 text-left">
                <div className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/40 text-xs text-foreground border border-border/40">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <span>Template Strict Preservation</span>
                </div>
                <div className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/40 text-xs text-foreground border border-border/40">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <span>Intelligent Role Detection</span>
                </div>
              </div>
            </div>
          )}

          {/* State 2: Processing Loader */}
          {isProcessing && (
            <div className="rounded-xl border border-border bg-card p-10 text-center shadow-xs space-y-6">
              <div className="relative w-16 h-16 mx-auto">
                <div className="w-16 h-16 rounded-full border-4 border-muted border-t-emerald-500 animate-spin" />
                <div className="absolute inset-0 flex items-center justify-center text-emerald-500">
                  <RefreshCw className="w-6 h-6 animate-pulse" />
                </div>
              </div>

              <div>
                <h3 className="text-base font-semibold text-foreground">
                  Running Comparison Pipeline...
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Extracting tables, parsing records, and reconciling underwriting census
                </p>
              </div>

              {/* Step Progression Indicators */}
              <div className="space-y-2 max-w-sm mx-auto text-left">
                {PIPELINE_STEPS.map((step, idx) => {
                  const isDone = idx < activeStep;
                  const isCurrent = idx === activeStep;
                  return (
                    <div
                      key={step}
                      className={`flex items-center gap-2.5 text-xs p-1.5 rounded transition-colors ${
                        isCurrent
                          ? "font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-500/10"
                          : isDone
                          ? "text-muted-foreground line-through opacity-80"
                          : "text-muted-foreground/60"
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isCurrent
                            ? "bg-emerald-500 animate-ping"
                            : isDone
                            ? "bg-emerald-500"
                            : "bg-muted-foreground/30"
                        }`}
                      />
                      <span>{step}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* State 3: Completed Results Dashboard */}
          {result && !isProcessing && (
            <div className="space-y-4">
              {/* Deliverable Action Banner - Redesigned with zero button congestion */}
              <div className="p-5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 shadow-xs space-y-3.5">
                {/* Header row: Status tag + Carrier badge + State */}
                <div className="flex flex-wrap items-center justify-between gap-2.5">
                  <div className="flex items-center gap-2">
                    <Badge className="bg-emerald-600 hover:bg-emerald-600 text-white text-[10.5px] font-semibold px-2.5 py-0.5 tracking-wide uppercase">
                      Pipeline Completed Successfully
                    </Badge>
                    {result.carrier && (
                      <Badge variant="outline" className="text-[10.5px] font-semibold border-purple-500/30 text-purple-600 dark:text-purple-400 bg-purple-500/10 px-2.5 py-0.5">
                        Carrier: {result.carrier}
                      </Badge>
                    )}
                  </div>
                  {result.state && (
                    <span className="text-xs text-muted-foreground font-mono">
                      State: {result.state}
                    </span>
                  )}
                </div>

                {/* File Title and Detailed Counts */}
                <div className="space-y-1">
                  <h3 className="text-sm md:text-base font-bold text-foreground font-mono break-all leading-snug">
                    {result.output_filename}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Completed Census with{" "}
                    <strong className="text-emerald-600 dark:text-emerald-400 font-bold">
                      {metrics.employees}
                    </strong>{" "}
                    employees and{" "}
                    <strong className="text-cyan-600 dark:text-cyan-400 font-bold">
                      {metrics.dependents}
                    </strong>{" "}
                    dependents.
                  </p>
                </div>

                {/* Dedicated Action Buttons Row - Generous padding and clean layout */}
                <div className="pt-2 border-t border-emerald-500/20 flex flex-wrap items-center gap-2.5">
                  <a
                    href={getDownloadUrl(result.download_xlsx_url)}
                    download
                    className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-colors shrink-0"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download Census (.xlsx)
                  </a>

                  {result.download_sbu_url && (
                    <a
                      href={getDownloadUrl(result.download_sbu_url)}
                      download
                      className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-xs transition-colors shrink-0"
                    >
                      <Download className="w-3.5 h-3.5" />
                      SBU Census (.xlsx)
                    </a>
                  )}

                  {result.download_email_url && (
                    <a
                      href={getDownloadUrl(result.download_email_url)}
                      download
                      className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold shadow-xs transition-colors shrink-0"
                    >
                      <Mail className="w-3.5 h-3.5 text-muted-foreground" />
                      Email (.txt)
                    </a>
                  )}

                  <a
                    href={getDownloadUrl(result.download_txt_url)}
                    download
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold shadow-xs transition-colors shrink-0"
                  >
                    <FileText className="w-3.5 h-3.5 text-muted-foreground" />
                    Exceptions (.txt)
                  </a>
                </div>
              </div>

              {/* 6 Metric Cards Grid - Accurate Numbers Parsed from Audit & Summary */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Census Employees
                  </span>
                  <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 block mt-0.5">
                    {metrics.employees}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Source rows: {metrics.srcEmployees}
                  </span>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Dependents
                  </span>
                  <span className="text-2xl font-bold text-cyan-600 dark:text-cyan-400 block mt-0.5">
                    {metrics.dependents}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Source rows: {metrics.srcDependents}
                  </span>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Missing from Invoice
                  </span>
                  <span className="text-2xl font-bold text-foreground block mt-0.5">
                    {metrics.missingInvoice}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Expected active
                  </span>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Missing from Census
                  </span>
                  <span className="text-2xl font-bold text-foreground block mt-0.5">
                    {metrics.missingCensus}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Invoice only
                  </span>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Tier Mismatches
                  </span>
                  <span className="text-2xl font-bold text-amber-600 dark:text-amber-400 block mt-0.5">
                    {metrics.tierMismatches}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Flagged in Col T
                  </span>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-card shadow-xs">
                  <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
                    Duplicate Employees
                  </span>
                  <span className="text-2xl font-bold text-foreground block mt-0.5">
                    {metrics.duplicateEmployees}
                  </span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5">
                    Deduped in output
                  </span>
                </div>
              </div>

              {/* Results Tabs: Summary, Email, Classified Files, Audit Notes */}
              <div className="rounded-xl border border-border bg-card shadow-xs overflow-hidden">
                <Tabs defaultValue="summary" className="w-full">
                  <div className="border-b border-border px-4 bg-muted/20">
                    <TabsList className="bg-transparent h-11 p-0 gap-4">
                      <TabsTrigger
                        value="summary"
                        className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-11 px-1 text-xs font-semibold"
                      >
                        Exception Summary
                      </TabsTrigger>
                      {result.email_text && (
                        <TabsTrigger
                          value="email"
                          className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-11 px-1 text-xs font-semibold"
                        >
                          Missing Information Email
                        </TabsTrigger>
                      )}
                      <TabsTrigger
                        value="files"
                        className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-11 px-1 text-xs font-semibold"
                      >
                        Classified Files ({result.classified_docs?.length ?? 0})
                      </TabsTrigger>
                      <TabsTrigger
                        value="audit"
                        className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none h-11 px-1 text-xs font-semibold"
                      >
                        Audit & Findings
                      </TabsTrigger>
                    </TabsList>
                  </div>

                  {/* Tab 1: Exception Summary */}
                  <TabsContent value="summary" className="p-4 m-0 space-y-2">
                    <div className="flex items-center justify-between pb-2 border-b border-border/40">
                      <span className="text-xs font-semibold text-foreground">
                        Brief Exception Summary (Console Output)
                      </span>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => copyToClipboard(result.summary, "Exception Summary")}
                        className="h-7 text-xs gap-1.5"
                      >
                        <Copy className="w-3 h-3" />
                        Copy
                      </Button>
                    </div>
                    <pre className="p-4 rounded-lg bg-muted/40 font-mono text-xs text-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap border border-border/40 max-h-80">
                      {result.summary}
                    </pre>
                  </TabsContent>

                  {/* Tab 2: Missing Information Email */}
                  {result.email_text && (
                    <TabsContent value="email" className="p-4 m-0 space-y-2">
                      <div className="flex items-center justify-between pb-2 border-b border-border/40">
                        <span className="text-xs font-semibold text-foreground">
                          Ready-to-Send Missing Information Email (Intake Deliverable)
                        </span>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => copyToClipboard(result.email_text || "", "Email")}
                          className="h-7 text-xs gap-1.5"
                        >
                          <Copy className="w-3 h-3" />
                          Copy Email
                        </Button>
                      </div>
                      <pre className="p-4 rounded-lg bg-muted/40 font-sans text-xs text-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap border border-border/40 max-h-80">
                        {result.email_text}
                      </pre>
                    </TabsContent>
                  )}

                  {/* Tab 3: Classified Files */}
                  <TabsContent value="files" className="p-4 m-0 space-y-3">
                    <p className="text-xs text-muted-foreground">
                      Structured text files are saved to{" "}
                      <span className="font-mono text-foreground font-semibold">
                        census_project/extracted_text/
                      </span>
                    </p>

                    <div className="border border-border/60 rounded-lg overflow-hidden">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-muted/50 border-b border-border/60 text-[11px] font-semibold text-muted-foreground uppercase">
                          <tr>
                            <th className="py-2.5 px-3">Filename</th>
                            <th className="py-2.5 px-3">Detected Role</th>
                            <th className="py-2.5 px-3">Extraction Mode</th>
                            <th className="py-2.5 px-3 text-right">Characters</th>
                            <th className="py-2.5 px-3 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40">
                          {result.classified_docs && result.classified_docs.length > 0 ? (
                            result.classified_docs.map((doc, idx) => (
                              <tr key={idx} className="hover:bg-muted/20 transition-colors">
                                <td className="py-2.5 px-3 font-medium text-foreground">
                                  {doc.filename || doc.name}
                                </td>
                                <td className="py-2.5 px-3">
                                  <Badge
                                    variant="secondary"
                                    className="text-[10px] uppercase font-bold tracking-wider py-0 px-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                                  >
                                    {doc.role || "DOCUMENT"}
                                  </Badge>
                                </td>
                                <td className="py-2.5 px-3 text-muted-foreground">
                                  {doc.mode || doc.extraction_method || "Direct Table Parsing"}
                                </td>
                                <td className="py-2.5 px-3 text-right font-mono text-muted-foreground">
                                  {(doc.char_count ?? doc.chars ?? 0).toLocaleString()}
                                </td>
                                <td className="py-2.5 px-3 text-right">
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => viewExtractedText(doc.filename || doc.name || "")}
                                    className="h-6 text-[11px] gap-1 px-2 text-primary hover:text-primary hover:bg-primary/10"
                                  >
                                    <Eye className="w-3 h-3" />
                                    View Text
                                  </Button>
                                </td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={5} className="py-6 text-center text-muted-foreground">
                                No classified files recorded.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </TabsContent>

                  {/* Tab 4: Audit & Findings */}
                  <TabsContent value="audit" className="p-4 m-0 space-y-2.5">
                    <span className="text-xs font-semibold text-foreground block pb-1 border-b border-border/40">
                      Audit Notes & Reconciliation Rules Triggered
                    </span>
                    {result.notes && result.notes.length > 0 ? (
                      <ul className="space-y-1.5">
                        {result.notes.map((note, idx) => (
                          <li
                            key={idx}
                            className="text-xs p-2.5 rounded-lg border border-border/40 bg-muted/20 flex items-start gap-2 leading-relaxed"
                          >
                            <span className="text-emerald-500 font-bold shrink-0">•</span>
                            <span className="text-foreground">{note}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground py-4 text-center">
                        No audit exceptions or discrepancy notes flagged.
                      </p>
                    )}
                  </TabsContent>
                </Tabs>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Extracted Text Dialog Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-6">
          <DialogHeader className="pb-3 border-b border-border">
            <DialogTitle className="text-base font-semibold flex items-center justify-between">
              <span>{modalTitle}</span>
              <span className="text-xs font-mono font-normal text-muted-foreground">
                {modalCharCount.toLocaleString()} chars
              </span>
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Raw structured text extracted during ingestion and document processing.
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto py-3">
            {modalLoading ? (
              <div className="py-12 flex flex-col items-center justify-center text-muted-foreground gap-2">
                <Loader2 className="w-6 h-6 animate-spin text-primary" />
                <span className="text-xs">Loading extracted text...</span>
              </div>
            ) : (
              <pre className="p-3 rounded-lg bg-muted/40 font-mono text-xs text-foreground whitespace-pre-wrap leading-relaxed border border-border/40">
                {modalText}
              </pre>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
            <Button
              size="sm"
              variant="outline"
              disabled={modalLoading || !modalText}
              onClick={() => copyToClipboard(modalText, "Extracted text")}
              className="gap-1.5 text-xs h-8"
            >
              <Copy className="w-3.5 h-3.5" />
              Copy Text
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setModalOpen(false)}
              className="text-xs h-8"
            >
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
