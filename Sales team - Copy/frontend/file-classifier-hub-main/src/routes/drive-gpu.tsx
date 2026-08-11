import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  HardDrive, Play, FileText, CheckCircle2, XCircle, Search, Cpu, Layers, AlertCircle, Loader2, ChevronDown, ChevronUp, Clock
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel, StatCard } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, getBackendUrl } from "@/lib/api";
import { useApp, useSettings, useAuth } from "@/lib/store";
import { toast } from "sonner";
import { FolderPickerModal } from "@/components/FolderPickerModal";
import type { DocumentFile } from "@/types/extractor";
import ResultsPanel from "@/components/ResultsPanel";
import UploadArea from "@/components/UploadArea";
import ProcessingStages from "@/components/ProcessingStages";
import MergeJsonButton from "@/components/MergeJsonButton";
import ClaimSummary from "@/components/ClaimSummary";

export const Route = createFileRoute("/drive-gpu")({ component: DriveGpuPage });

function DriveGpuPage() {
  const { user } = useAuth();
  const search = Route.useSearch() as any;
  const pipeline = search.pipeline || "";

  let pageTitle = "GPU-Accelerated Drive";
  if (pipeline === "INSURANCE") pageTitle = "Loss Run";
  else if (pipeline === "BANK_STATEMENT") pageTitle = "Bank Statement";
  else if (pipeline === "INVOICE") pageTitle = "Benefit Invoice Extraction";
  else if (pipeline === "WORK_COMP") pageTitle = "Accord 130";
  else if (pipeline === "VENDOR_INVOICE") pageTitle = "Vendor Invoice";

  const defaultIn = useSettings((s) => s.defaultInputFolder);
  const defaultOut = useSettings((s) => s.defaultOutputFolder);

  const [input, setInput] = useState(defaultIn || "");
  const [output, setOutput] = useState(defaultOut || "");
  const [maxPages, setMaxPages] = useState(3);
  const [model, setModel] = useState("gpt-4o");
  const [minScore, setMinScore] = useState(3.0);
  
  const [running, setRunning] = useState(false);
  const [processedDocs, setProcessedDocs] = useState<DocumentFile[]>([]);
  const [activeDocName, setActiveDocName] = useState<string | null>(null);
  const [expandedDocName, setExpandedDocName] = useState<string | null>(null);

  // Merged state
  const [mergedSummary, setMergedSummary] = useState<string | null>(null);
  const [isMerging, setIsMerging] = useState(false);

  // Folder Picker States
  const [localPickerOpen, setLocalPickerOpen] = useState(false);
  const [localPickerType, setLocalPickerType] = useState<"input" | "output">("input");

  const addLog = useApp((s) => s.addLog);
  const addActivity = useApp((s) => s.addActivity);

  // Local Drive Status Query
  const status = useQuery({
    queryKey: ["gpu-drive-status", input],
    queryFn: () => api.gpuDriveStatus(input || undefined),
    enabled: !!input,
    retry: false,
    refetchInterval: 10000, // Poll status every 10 seconds
  });

  const isConnected = status.data?.connected ?? false;
  const pdfCount = status.data?.pdf_count ?? 0;
  const pdfFiles = status.data?.pdf_files || [];

  // Reset document list when input folder changes (to clear stale results)
  useEffect(() => {
    setProcessedDocs([]);
    setActiveDocName(null);
    setExpandedDocName(null);
    setMergedSummary(null);
  }, [input]);

  // Extraction processing core for a single file object
  const processSingleFileObj = async (file: File) => {
    try {
      setProcessedDocs((prev) =>
        prev.map((d) =>
          d.name === file.name
            ? {
                ...d,
                stage: "classification",
                stageMessage: "Uploading & Classifying...",
                progress: 15,
                error: null
              }
            : d
        )
      );

      const userEmail = user?.email || "SYSTEM";
      const res = await api.gpuExtractDirect(file, pipeline, userEmail);
      
      // Fetch JSON contents
      let schema: any = null;
      if (res.output_json) {
        try {
          const schemaResponse = await fetch(`${getBackendUrl()}/api/gpu/api/download/${res.output_json}`);
          schema = await schemaResponse.json();
        } catch (e) {
          console.error("Failed to fetch schema for direct file:", e);
        }
      }

      const docType = res.type || "UNKNOWN";

      const docUpdate: Partial<DocumentFile> = {
        stage: "complete",
        stageMessage: "Extraction complete",
        progress: 100,
        result: schema,
        metadata: {
          insurer: res.insurer || "Uploaded Document",
          format: docType.toLowerCase(),
          confidence: 95,
          claims_count: res.claims_count,
          total_value: res.total_value,
          documentType: docType,
          work_comp_metadata: res.work_comp_metadata
        },
        excelPath: res.output_file,
        jsonPath: res.output_json,
        excelUrl: res.excel,
        jsonUrl: res.json,
        completedAt: Date.now()
      };

      setProcessedDocs((prev) =>
        prev.map((d) => (d.name === file.name ? { ...d, ...docUpdate } : d))
      );

      toast.success(`Successfully processed ${file.name}`);
      addActivity({
        kind: "drive",
        title: "Direct GPU upload complete",
        detail: `Processed: ${file.name}`,
      });
      addLog("INFO", "drive", `Direct GPU upload classification completed successfully for ${file.name}`, res);
    } catch (err: any) {
      toast.error(`Failed to process ${file.name}: ${err.message || err}`);
      setProcessedDocs((prev) =>
        prev.map((d) =>
          d.name === file.name
            ? {
                ...d,
                stage: "error",
                stageMessage: "Extraction failed",
                progress: 100,
                error: err.message || "Failed to process document through GPU pipeline"
              }
              : d
          )
        );
        addLog("ERROR", "drive", `Direct upload failed for ${file.name}: ${err.message || err}`);
    }
  };

  // Handle files selected via Drag & Drop Upload Area
  const handleFilesSelected = async (files: File[]) => {
    if (files.length === 0) return;

    // Create queue items for files being uploaded
    const newDocs: DocumentFile[] = files.map((file) => ({
      id: file.name,
      name: file.name,
      size: file.size,
      stage: "queued",
      stageMessage: "Queued",
      progress: 0,
      result: null,
      error: null,
      startedAt: Date.now(),
      completedAt: null,
      file: file // Save the raw File object for reprocessing!
    }));

    setProcessedDocs((prev) => [...prev, ...newDocs]);
    setActiveDocName(files[0].name);

    // Process files sequentially
    for (const file of files) {
      await processSingleFileObj(file);
    }
  };

  // Run Folder Watch Ingestion Pipeline
  async function run() {
    if (!input || !output) {
      return toast.error("Please configure both input and output directories.");
    }
    setRunning(true);
    setProcessedDocs([]);
    setActiveDocName(null);
    setMergedSummary(null);
    
    // Set temporary "processing" stage for files in folder
    const initialDocs: DocumentFile[] = pdfFiles.map((filename) => ({
      id: filename,
      name: filename,
      size: 0,
      stage: "classification",
      stageMessage: "Processing under GPU pipeline...",
      progress: 20,
      result: null,
      error: null,
      startedAt: Date.now(),
      completedAt: null
    }));
    setProcessedDocs(initialDocs);

    try {
      const r = await api.gpuDriveClassify({
        input_folder: input,
        output_folder: output,
        max_pages: maxPages,
        min_score: minScore,
        model: model,
      });

      const docs: DocumentFile[] = (r.results || []).map((res: any) => ({
        id: res.file_name,
        name: res.file_name,
        size: 0,
        stage: res.status === "success" ? "complete" : "error",
        stageMessage: res.status === "success" ? "Extraction complete" : "Extraction failed",
        progress: 100,
        result: res.result || null,
        metadata: res.metadata,
        error: res.error || null,
        startedAt: Date.now(),
        completedAt: Date.now(),
        excelPath: res.excel_path,
        jsonPath: res.json_path,
        excelUrl: res.excel_url,
        jsonUrl: res.json_url
      }));

      setProcessedDocs(docs);

      // Select first successfully processed document
      if (docs.length > 0) {
        const firstSuccess = docs.find((d) => d.stage === "complete");
        if (firstSuccess) {
          setActiveDocName(firstSuccess.name);
        } else {
          setActiveDocName(docs[0].name);
        }
      }

      addActivity({
        kind: "drive",
        title: "GPU Drive processing complete",
        detail: `Successfully processed ${docs.filter(d => d.stage === "complete").length} of ${docs.length} files.`,
      });
      addLog("INFO", "drive", "GPU Drive pipeline run complete", r);
      toast.success("GPU Drive extraction run completed successfully!");
      status.refetch();
    } catch (e: any) {
      toast.error(e.message || "GPU execution run failed");
      addLog("ERROR", "drive", e.message || "GPU execution run failed");
      // Mark all as error
      setProcessedDocs(pdfFiles.map((filename) => ({
        id: filename,
        name: filename,
        size: 0,
        stage: "error",
        stageMessage: "Execution failed",
        progress: 100,
        result: null,
        error: e.message || "Failed to call backend classifier API",
        startedAt: Date.now(),
        completedAt: Date.now()
      })));
    } finally {
      setRunning(false);
    }
  }

  // Clear workspace
  const handleResetWorkspace = () => {
    setProcessedDocs([]);
    setActiveDocName(null);
    setExpandedDocName(null);
    setMergedSummary(null);
    toast.success("Workspace reset successfully");
  };

  // Reprocess a single file
  const reprocessDocument = async (filename: string) => {
    const doc = queueDocs.find((d) => d.name === filename);
    if (!doc) return;

    if (doc.file) {
      toast.info(`Reprocessing uploaded document: ${filename}`);
      await processSingleFileObj(doc.file);
    } else {
      toast.info(`Reprocessing folder document: ${filename}`);
      // For local files, since the server has the files, we re-run the folder pipeline
      run();
    }
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

  // Build the unified queue list matching actual directory files (plus uploaded files) with processing status
  const queueDocs: DocumentFile[] = [];

  // 1. Add direct uploads or processed results in status
  processedDocs.forEach((d) => {
    if (!queueDocs.some((existing) => existing.name === d.name)) {
      queueDocs.push(d);
    }
  });

  // 2. Add staged files in local watch directory that aren't processed yet
  pdfFiles.forEach((filename) => {
    if (!queueDocs.some((existing) => existing.name === filename)) {
      queueDocs.push({
        id: filename,
        name: filename,
        size: 0,
        stage: "queued",
        stageMessage: "Queued",
        progress: 0,
        result: null,
        error: null,
        startedAt: null,
        completedAt: null
      });
    }
  });

  const activeDoc = queueDocs.find((d) => d.name === activeDocName) || null;

  // --- Category-Aware Merge Logic ---
  const completedDocs = queueDocs.filter((d) => d.stage === "complete" && d.result);

  const getMergeCategory = (type?: string) => {
    if (!type) return "UNKNOWN";
    const t = type.toUpperCase();
    if (t === "INSURANCE" || t === "INSURANCE_CLAIMS") return "INSURANCE";
    if (t === "WORK_COMPENSATION") return "WORK_COMPENSATION";
    if (t === "INVOICE" || t === "VENDOR_INVOICE") return "INVOICE";
    return t;
  };

  const activeDocCategory = activeDoc ? getMergeCategory(activeDoc.metadata?.documentType) : null;
  const docsInSameCategory = completedDocs.filter(d => getMergeCategory(d.metadata?.documentType) === activeDocCategory);
  
  const isMergeable = docsInSameCategory.length >= 2;
  const hasMultipleDocs = completedDocs.length >= 2;
  const sharedType = isMergeable ? activeDocCategory || undefined : undefined;

  const getAllClaims = useCallback(() => {
    return docsInSameCategory.flatMap((d) => {
      const result = d.result;
      const metadata = d.metadata;
      const category = getMergeCategory(metadata?.documentType);

      if (category === "WORK_COMPENSATION") {
        const wcData = (result as any)?.data || {};
        return wcData.ratingByState || [];
      }
      if (category === "INSURANCE") {
        return (result as any)?.claims || [];
      }
      return Array.isArray(result) ? result : [];
    });
  }, [docsInSameCategory]);

  const handleDownloadMergedJson = useCallback(() => {
    const claims = getAllClaims();
    const blob = new Blob([JSON.stringify(claims, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `merged_${activeDocCategory?.toLowerCase() || "data"}_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [getAllClaims, activeDocCategory]);

  const handleDownloadMergedCsv = useCallback(() => {
    const claims = getAllClaims();
    if (claims.length === 0) return;

    const headers = Array.from(new Set(claims.flatMap(c => Object.keys(c))));
    const csvRows = [
      headers.join(','),
      ...claims.map(row =>
        headers.map(header => {
          const val = row[header];
          const escaped = ('' + (val ?? '')).replace(/"/g, '""');
          return `"${escaped}"`;
        }).join(',')
      )
    ];

    const blob = new Blob([csvRows.join('\n')], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `merged_${activeDocCategory?.toLowerCase() || "data"}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [getAllClaims, activeDocCategory]);

  const handleTriggerMergeAnalysis = useCallback(async () => {
    const claims = getAllClaims();
    if (claims.length === 0) {
      toast.error("No claims data found to analyze");
      return;
    }

    setIsMerging(true);
    setMergedSummary(null);
    try {
      const response = await fetch(`${getBackendUrl()}/api/gpu/api/claim-summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claims }),
      });

      const data = await response.json();
      if (data.success && data.summary) {
        setMergedSummary(data.summary);
        toast.success("Merged AI Summary generated!");
      } else {
        toast.error("Failed to generate summary: " + (data.error || "Unknown error"));
      }
    } catch (error) {
      console.error("Error generating merged summary:", error);
      toast.error("Error connecting to summary service");
    } finally {
      setIsMerging(false);
    }
  }, [getAllClaims]);

  return (
    <div className="space-y-4">
      <PageHeader
        icon={HardDrive}
        title={pageTitle}
        description="Process loss runs, ACORDs, invoices, and bank statements in a local folder or via direct file upload using the high-performance GPU extraction pipeline."
      />

      {/* Top Section: Upload Area */}
      <div className="mb-4">
        <UploadArea onFilesSelected={handleFilesSelected} disabled={running} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Left Side: Queue list */}
        <div className="space-y-3">
          <Panel
            title={`Document Queue (${queueDocs.length})`}
            description="Expand items to view detailed processing checklist stages"
          >
            {queueDocs.length > 0 ? (
              <div className="space-y-3">
                <div className="border border-border rounded-lg divide-y max-h-96 overflow-y-auto min-h-[120px] bg-card/50">
                  {queueDocs.map((doc) => {
                    const isActive = activeDocName === doc.name;
                    const isExpanded = expandedDocName === doc.name;
                    const isCompleted = doc.stage === "complete";
                    const isFailed = doc.stage === "error";
                    const isProcessing = doc.stage !== "queued" && doc.stage !== "complete" && doc.stage !== "error";

                    return (
                      <div
                        key={doc.name}
                        className={`transition-all duration-200 ${
                          isActive
                            ? "bg-primary/5 border-l-2 border-primary"
                            : "hover:bg-muted/20"
                        }`}
                      >
                        <div
                          className="p-2.5 flex items-center justify-between text-xs cursor-pointer"
                          onClick={() => {
                            if (isCompleted || isFailed) {
                              setActiveDocName(doc.name);
                            }
                          }}
                        >
                          <div className="flex items-center gap-2 truncate flex-1 min-w-0">
                            <FileText className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                            <div className="flex flex-col truncate min-w-0">
                              <span className={`truncate ${isActive ? "font-semibold text-primary" : "text-foreground"}`}>
                                {doc.name}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {doc.size > 0 ? `${(doc.size / (1024 * 1024)).toFixed(2)} MB` : "Local file"}
                                {isCompleted && doc.metadata?.claims_count !== undefined && (
                                  <> • {doc.metadata.claims_count} entries</>
                                )}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0 ml-2">
                            {isCompleted ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 font-semibold border border-emerald-500/20">
                                Complete
                              </span>
                            ) : isFailed ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/10 text-red-600 font-semibold border border-red-500/20">
                                Error
                              </span>
                            ) : isProcessing ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-600 font-semibold border border-blue-500/20 flex items-center gap-1">
                                <Loader2 className="w-2.5 h-2.5 animate-spin" /> Processing
                              </span>
                            ) : (
                              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-semibold border border-border">
                                Staged
                              </span>
                            )}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedDocName(isExpanded ? null : doc.name);
                              }}
                              className="text-muted-foreground hover:text-foreground p-0.5 hover:bg-muted rounded"
                            >
                              {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        </div>
                        {isExpanded && doc.stage !== "queued" && (
                          <div className="px-3 pb-3 border-t border-border/40 pt-2 bg-muted/10">
                            <ProcessingStages currentStage={doc.stage} stageMessage={doc.stageMessage} />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <MergeJsonButton
                  completedDocsCount={docsInSameCategory.length}
                  isMergeable={isMergeable}
                  sharedType={sharedType}
                  onDownloadJson={handleDownloadMergedJson}
                  onDownloadCsv={handleDownloadMergedCsv}
                  onTriggerMergeAnalysis={handleTriggerMergeAnalysis}
                  isAnalyzing={isMerging}
                  onResetWorkspace={handleResetWorkspace}
                />
              </div>
            ) : (
              <div className="text-[12px] text-muted-foreground text-center py-12 flex flex-col gap-2 justify-center items-center">
                <AlertCircle className="w-8 h-8 text-muted-foreground opacity-40" />
                <span>Upload files or scan a watched folder to get started.</span>
              </div>
            )}
          </Panel>
        </div>

        {/* Right Side: Execution Results Viewer */}
        <div className="lg:col-span-2 space-y-4">
          <Panel
            title={activeDoc ? `Results — ${activeDoc.name}` : "Extraction Results"}
            description="Detailed parsed data grid, insurance summary, and JSON files for the selected document"
            className="h-full"
          >
            {!isMergeable && hasMultipleDocs && (
              <div className="mb-4 p-2.5 rounded-lg bg-amber-500/5 border border-amber-500/10 text-[11px] text-amber-600 flex items-start gap-2 italic">
                <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <div>
                  <span className="font-bold">Note:</span> Mixed document types (e.g. Invoice + Loss Run) cannot be merged or cross-analyzed.
                </div>
              </div>
            )}
            
            {activeDoc ? (
              <ResultsPanel
                document={activeDoc}
                onReprocess={reprocessDocument}
                mergedSummary={mergedSummary}
                isMerging={isMerging}
                onTriggerMergeAnalysis={handleTriggerMergeAnalysis}
                onDownloadMergedJson={handleDownloadMergedJson}
                onDownloadMergedCsv={handleDownloadMergedCsv}
                hasMultipleDocs={hasMultipleDocs && isMergeable}
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-32 text-muted-foreground gap-3">
                <HardDrive className="w-12 h-12 opacity-30" />
                <p className="text-sm">Select a processed document from the queue to view details</p>
              </div>
            )}
          </Panel>

      {/* Merged AI Claims Analysis Report Panel */}
          {mergedSummary && (
            <ClaimSummary summary={mergedSummary} onClose={() => setMergedSummary(null)} />
          )}
        </div>
      </div>
    </div>
  );
}
