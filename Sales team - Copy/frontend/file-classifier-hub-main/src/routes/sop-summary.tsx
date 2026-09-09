import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import {
  UploadCloud, FileText, CheckCircle2, Loader2, Download,
  RotateCw, Trash2, Sparkles, FileCheck, Shield, CheckSquare,
  Clock, Cpu, ArrowRight, ExternalLink, Layers, Copy, Check,
  Info, FileSpreadsheet, FileCode2, FileDown, Mail, User, Briefcase
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getBackendUrl } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/sop-summary")({
  component: SopSummaryPage,
});

interface DynamicSection {
  header: string;
  summary: string | string[] | any;
}

interface SopSummaryData {
  title?: string;
  process_overview?: {
    System?: any;
    Trigger?: any;
    TAT?: any;
    Accuracy?: any;
    [key: string]: any;
  };
  dynamic_sections?: DynamicSection[];
  quick_checklist?: any[];
  special_cases?: any;
  full_sop_link?: any;
  frequency?: any;
  contact?: any;
  [key: string]: any;
}

/**
 * Safely format any JSON value (string, object, array, number) into a human-readable string.
 */
function formatFieldValue(val: any, fallback = "N/A"): string {
  if (val === null || val === undefined || val === "") return fallback;
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  if (Array.isArray(val)) {
    return val.map((v) => (typeof v === "object" ? formatFieldValue(v) : String(v))).join(", ");
  }
  if (typeof val === "object") {
    const parts: string[] = [];
    if (val.name) parts.push(val.name);
    if (val.designation || val.title || val.role) parts.push(`(${val.designation || val.title || val.role})`);
    if (val.email) parts.push(`<${val.email}>`);
    if (val.phone) parts.push(val.phone);
    if (parts.length > 0) return parts.join(" ");

    return Object.entries(val)
      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`)
      .join(" • ");
  }
  return String(val);
}

function SopSummaryPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [summaryResult, setSummaryResult] = useState<SopSummaryData | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [downloadUrls, setDownloadUrls] = useState<Record<string, string>>({});
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".docx")) {
      toast.error("Please upload a .docx Standard Operating Procedure file");
      return;
    }
    setSelectedFile(file);
    toast.success(`Selected file: ${file.name}`);
  };

  const handleSummarize = async () => {
    if (!selectedFile) {
      toast.error("Please select a .docx file first");
      return;
    }

    setIsProcessing(true);
    const toastId = toast.loading("Analyzing SOP document with AI & generating templates...");

    try {
      const response = await api.summarizeSop(selectedFile);
      setSummaryResult(response.summary);
      setSessionId(response.session_id);
      setDownloadUrls(response.download_urls);
      toast.success("SOP parsed and summary generated successfully!", { id: toastId });
    } catch (err: any) {
      console.error("Error summarizing SOP:", err);
      toast.error(`Processing failed: ${err.message || "Unknown error"}`, { id: toastId });
    } finally {
      setIsProcessing(false);
    }
  };

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleDownload = (type: string, customFilename?: string) => {
    if (!sessionId) {
      toast.error("No active session to download files for");
      return;
    }
    const backend = getBackendUrl();
    const url = `${backend}/api/summary/download/${encodeURIComponent(sessionId)}/${type}`;

    // Trigger immediate direct download
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.setAttribute("download", customFilename || `${sessionId}_${type}`);
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    toast.success(`Downloading ${type.replace("_", " ").toUpperCase()} file...`);
  };

  const clearCurrent = () => {
    setSelectedFile(null);
    setSummaryResult(null);
    setSessionId("");
    setDownloadUrls({});
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-y-auto bg-background/50 p-6 space-y-6">
      <PageHeader
        title="SOP Summarizer"
        description="Transform complex Standard Operating Procedure (.docx) documents into executive summaries, structured procedures, process checklists, and multi-format reports."
        icon={FileText}
      />

      {/* Top Upload & Actions Control Bar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Dropzone & Upload Panel */}
        <Panel title="Upload SOP Document (.docx)" className="lg:col-span-2">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              handleFileSelect(e.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-border rounded-xl p-6 flex flex-col items-center justify-center text-center cursor-pointer hover:border-primary/50 hover:bg-primary/5 transition-all group"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files)}
            />
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3 group-hover:scale-110 transition-transform">
              <UploadCloud className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-foreground">
              {selectedFile ? selectedFile.name : "Drag & drop your SOP Word Document (.docx) here"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {selectedFile
                ? `${formatFileSize(selectedFile.size)} • Click or drop again to replace`
                : "Supports Microsoft Word (.docx) documents up to 50MB"}
            </p>
          </div>

          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-2">
              {selectedFile && (
                <Button variant="outline" size="sm" onClick={clearCurrent} disabled={isProcessing}>
                  <Trash2 className="w-4 h-4 mr-1 text-destructive" /> Clear
                </Button>
              )}
            </div>

            <Button
              onClick={handleSummarize}
              disabled={!selectedFile || isProcessing}
              className="gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-md"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Analyzing & Generating...
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" /> Generate Structured Summary
                </>
              )}
            </Button>
          </div>
        </Panel>

        {/* Quick Export / Download Hub */}
        <Panel title="Export & Artifact Hub">
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Export generated summaries into multiple business-ready formats or download the merged package.
            </p>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("zip", `${sessionId}_summary_files.zip`)}
              >
                <FileDown className="w-4 h-4 text-emerald-500" /> Full ZIP (.zip)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("summary_docx", `${sessionId}_summary_filled.docx`)}
              >
                <FileText className="w-4 h-4 text-blue-500" /> Word Summary (.docx)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("combined_docx", `${sessionId}_combined_summary.docx`)}
              >
                <FileText className="w-4 h-4 text-indigo-500" /> Merged SOP (.docx)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("pdf", `${sessionId}_summary.pdf`)}
              >
                <FileText className="w-4 h-4 text-rose-500" /> PDF Report (.pdf)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("html", `${sessionId}_summary.html`)}
              >
                <FileCode2 className="w-4 h-4 text-amber-500" /> HTML View (.html)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs"
                disabled={!sessionId}
                onClick={() => handleDownload("json", `${sessionId}_summary.json`)}
              >
                <FileCode2 className="w-4 h-4 text-purple-500" /> JSON Data (.json)
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="justify-start gap-2 h-9 text-xs col-span-2"
                disabled={!sessionId}
                onClick={() => handleDownload("txt", `${sessionId}_summary.txt`)}
              >
                <FileText className="w-4 h-4 text-gray-500" /> Plain Text (.txt)
              </Button>
            </div>

            {sessionId ? (
              <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-600 dark:text-emerald-400 flex items-center gap-2 mt-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>Session Active: <strong>{sessionId}</strong></span>
              </div>
            ) : (
              <div className="p-2.5 rounded-lg bg-muted/40 border border-border text-[11px] text-muted-foreground flex items-center gap-2 mt-2">
                <Info className="w-4 h-4 shrink-0" />
                <span>Artifacts will unlock once a document is summarized.</span>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid grid-cols-2 max-w-xs mb-4">
          <TabsTrigger value="overview" className="gap-1.5 text-xs">
            <Layers className="w-3.5 h-3.5" /> Structured Summary
          </TabsTrigger>
          <TabsTrigger value="raw" className="gap-1.5 text-xs">
            <FileCode2 className="w-3.5 h-3.5" /> Raw JSON Schema
          </TabsTrigger>
        </TabsList>

        {/* TAB 1: Structured Summary & Procedures */}
        <TabsContent value="overview" className="space-y-6">
          {summaryResult ? (
            <div className="space-y-6">
              {/* Header Overview Card */}
              <div className="p-6 rounded-2xl border border-border bg-gradient-to-br from-card/90 via-card/50 to-background shadow-sm space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/60 pb-4">
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-primary/10 text-primary">
                      Standard Operating Procedure
                    </span>
                    <h2 className="text-xl font-bold text-foreground mt-1">
                      {formatFieldValue(summaryResult.title, "Process Summary")}
                    </h2>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {summaryResult.process_overview?.System && (
                      <Badge variant="secondary" className="gap-1 bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20">
                        <Cpu className="w-3 h-3" /> System: {formatFieldValue(summaryResult.process_overview.System)}
                      </Badge>
                    )}
                    {summaryResult.process_overview?.Trigger && (
                      <Badge variant="secondary" className="gap-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20">
                        <Clock className="w-3 h-3" /> Trigger: {formatFieldValue(summaryResult.process_overview.Trigger)}
                      </Badge>
                    )}
                    {summaryResult.process_overview?.TAT && (
                      <Badge variant="secondary" className="gap-1 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20">
                        TAT: {formatFieldValue(summaryResult.process_overview.TAT)}
                      </Badge>
                    )}
                    {summaryResult.process_overview?.Accuracy && (
                      <Badge variant="secondary" className="gap-1 bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20">
                        Accuracy: {formatFieldValue(summaryResult.process_overview.Accuracy)}
                      </Badge>
                    )}
                  </div>
                </div>

                {/* Additional Metadata Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                  <div className="p-3 rounded-lg bg-muted/40 border border-border">
                    <span className="text-muted-foreground block text-[11px] mb-0.5">Execution Frequency</span>
                    <span className="font-semibold text-foreground">
                      {formatFieldValue(summaryResult.frequency, "As Triggered / Per Schedule")}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-muted/40 border border-border">
                    <span className="text-muted-foreground block text-[11px] mb-0.5">Primary Contact / Escalation</span>
                    {typeof summaryResult.contact === "object" && summaryResult.contact !== null ? (
                      <div className="space-y-0.5 font-medium text-foreground">
                        {summaryResult.contact.name && (
                          <div className="flex items-center gap-1 font-semibold">
                            <User className="w-3 h-3 text-primary shrink-0" />
                            <span>{summaryResult.contact.name}</span>
                          </div>
                        )}
                        {summaryResult.contact.designation && (
                          <div className="flex items-center gap-1 text-muted-foreground text-[11px]">
                            <Briefcase className="w-3 h-3 shrink-0" />
                            <span>{summaryResult.contact.designation}</span>
                          </div>
                        )}
                        {summaryResult.contact.email && (
                          <div className="flex items-center gap-1 text-blue-600 dark:text-blue-400 text-[11px]">
                            <Mail className="w-3 h-3 shrink-0" />
                            <a href={`mailto:${summaryResult.contact.email}`} className="hover:underline">
                              {summaryResult.contact.email}
                            </a>
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="font-semibold text-foreground">
                        {formatFieldValue(summaryResult.contact, "Standard SOP Team / Payroll Admin")}
                      </span>
                    )}
                  </div>

                  <div className="p-3 rounded-lg bg-muted/40 border border-border">
                    <span className="text-muted-foreground block text-[11px] mb-0.5">Full SOP Reference</span>
                    <span
                      className="font-semibold text-foreground truncate block"
                      title={formatFieldValue(summaryResult.full_sop_link, "Internal Document Repository")}
                    >
                      {formatFieldValue(summaryResult.full_sop_link, "Internal Document Repository")}
                    </span>
                  </div>
                </div>
              </div>

              {/* Procedures and Checklist 2-Column Section */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Procedures Column */}
                <div className="lg:col-span-2 space-y-4">
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                    <Layers className="w-4 h-4 text-primary" /> Dynamic Step-by-Step Procedures
                  </h3>

                  {summaryResult.dynamic_sections && summaryResult.dynamic_sections.length > 0 ? (
                    <div className="space-y-3">
                      {summaryResult.dynamic_sections.map((sec, idx) => {
                        const headerText = formatFieldValue(sec.header, `Procedure ${idx + 1}`);
                        const summaryContent = Array.isArray(sec.summary)
                          ? sec.summary.map((item) => formatFieldValue(item))
                          : typeof sec.summary === "object" && sec.summary !== null
                          ? formatFieldValue(sec.summary)
                          : String(sec.summary || "");

                        return (
                          <div
                            key={idx}
                            className="p-4 rounded-xl border border-border bg-card/60 hover:bg-card/90 transition-all shadow-sm space-y-2"
                          >
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-bold text-foreground flex items-center gap-2">
                                <span className="w-5 h-5 rounded-full bg-primary/10 text-primary text-[11px] flex items-center justify-center font-mono">
                                  {idx + 1}
                                </span>
                                {headerText}
                              </h4>
                              <button
                                onClick={() =>
                                  copyToClipboard(
                                    Array.isArray(summaryContent) ? summaryContent.join("\n") : summaryContent,
                                    `sec-${idx}`
                                  )
                                }
                                className="text-muted-foreground hover:text-foreground p-1 rounded hover:bg-muted"
                                title="Copy procedure text"
                              >
                                {copiedKey === `sec-${idx}` ? (
                                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                                ) : (
                                  <Copy className="w-3.5 h-3.5" />
                                )}
                              </button>
                            </div>

                            <div className="text-xs text-muted-foreground leading-relaxed pl-7">
                              {Array.isArray(summaryContent) ? (
                                <ul className="list-disc space-y-1 pl-4">
                                  {summaryContent.map((pt, pIdx) => (
                                    <li key={pIdx}>{pt}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="whitespace-pre-line">{summaryContent}</p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="p-6 text-center text-xs text-muted-foreground border border-dashed rounded-xl">
                      No sub-procedures were extracted from this document.
                    </div>
                  )}
                </div>

                {/* Right Column: Quick Checklist & Special Cases */}
                <div className="space-y-6">
                  {/* Quick Checklist */}
                  <Panel title="Quick Procedure Checklist" icon={CheckSquare}>
                    {summaryResult.quick_checklist && summaryResult.quick_checklist.length > 0 ? (
                      <ul className="space-y-2 text-xs">
                        {summaryResult.quick_checklist.map((item, idx) => (
                          <li
                            key={idx}
                            className="p-2.5 rounded-lg border border-border bg-card/40 flex items-start gap-2.5 hover:bg-card transition-colors"
                          >
                            <input
                              type="checkbox"
                              id={`check-${idx}`}
                              className="mt-0.5 rounded border-input text-primary focus:ring-primary/40 cursor-pointer"
                            />
                            <label htmlFor={`check-${idx}`} className="cursor-pointer text-foreground/90 select-none">
                              {formatFieldValue(item)}
                            </label>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-xs text-muted-foreground">No checklist items generated.</p>
                    )}
                  </Panel>

                  {/* Special Cases & Exceptions */}
                  <Panel title="Special Cases & Exceptions" icon={Shield}>
                    {summaryResult.special_cases ? (
                      <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-900 dark:text-amber-200 leading-relaxed">
                        {Array.isArray(summaryResult.special_cases) ? (
                          <ul className="list-disc pl-4 space-y-1">
                            {summaryResult.special_cases.map((sc, scIdx) => (
                              <li key={scIdx}>{formatFieldValue(sc)}</li>
                            ))}
                          </ul>
                        ) : (
                          <p>{formatFieldValue(summaryResult.special_cases)}</p>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">No special edge cases noted in document.</p>
                    )}
                  </Panel>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center rounded-2xl border border-dashed border-border bg-card/20 space-y-3">
              <FileText className="w-10 h-10 text-muted-foreground mx-auto" />
              <h3 className="text-sm font-semibold text-foreground">No SOP Document Analyzed Yet</h3>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                Upload your standard operating procedure (.docx) above and click <strong>Generate Structured Summary</strong> to view parsed procedures, checklist, and metadata.
              </p>
            </div>
          )}
        </TabsContent>

        {/* TAB 2: Raw JSON Schema View */}
        <TabsContent value="raw">
          <Panel title="Structured JSON Extraction" icon={FileCode2}>
            {summaryResult ? (
              <div className="relative">
                <button
                  onClick={() => copyToClipboard(JSON.stringify(summaryResult, null, 2), "raw-json")}
                  className="absolute top-2 right-2 px-2.5 py-1 text-xs rounded bg-muted hover:bg-muted/80 border border-border flex items-center gap-1 text-foreground"
                >
                  {copiedKey === "raw-json" ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  Copy JSON
                </button>
                <pre className="p-4 rounded-xl bg-slate-950 text-slate-100 text-xs overflow-x-auto font-mono max-h-[500px]">
                  {JSON.stringify(summaryResult, null, 2)}
                </pre>
              </div>
            ) : (
              <div className="p-6 text-center text-xs text-muted-foreground">
                No JSON data available. Summarize a document first.
              </div>
            )}
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
