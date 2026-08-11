import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import {
  FileCheck, UploadCloud, FileText, CheckCircle2, Loader2, Download,
  Check, Clock, Code, Table, ShieldCheck, Copy, AlertCircle, FileJson, Layers
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, getBackendUrl } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/payroll-extractor")({
  component: PayrollExtractorPage,
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
  { label: "Document Verification", subtext: "Checking PDF format..." },
  { label: "Vision Processing", subtext: "Extracting tables and handwritten notes..." },
  { label: "Data Structuring", subtext: "Mapping to payroll schema..." },
  { label: "Complete", subtext: "Extraction completed successfully." },
];

export function PayrollExtractorPage() {
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

    const primary = array.find((f) => f.name.toLowerCase().endsWith(".pdf")) || array[0];
    const totalBytes = array.reduce((acc, f) => acc + f.size, 0);

    const newItem: FlowQueueItem = {
      id: Math.random().toString(36).substring(2, 9),
      files: array,
      primaryName: primary.name,
      displayName: `Payroll: ${primary.name}`,
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
    toast.success(`Added file(s) for Payroll Extraction`);
  };

  const processQueue = async () => {
    if (!activeItem) {
      toast.info("Please select a file to process.");
      return;
    }

    if (activeItem.status === "complete") {
      toast.info("Selected file is already processed.");
      return;
    }

    setIsProcessing(true);
    const item = activeItem;

    setQueue((prev) =>
      prev.map((q) =>
        q.id === item.id
          ? { ...q, status: "processing", statusText: STEPPER_STAGES[0].subtext, stageIdx: 0 }
          : q
      )
    );

    for (let stage = 0; stage < STEPPER_STAGES.length - 1; stage++) {
      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? { ...q, stageIdx: stage, statusText: STEPPER_STAGES[stage].subtext }
            : q
        )
      );
      await new Promise((r) => setTimeout(r, 600));
    }

    try {
      // Assuming primary file is a PDF
      const pdfFile = item.files.find(f => f.name.toLowerCase().endsWith('.pdf')) || item.files[0];
      const res = await api.processPayrollPdf(pdfFile);

      setQueue((prev) =>
        prev.map((q) =>
          q.id === item.id
            ? {
                ...q,
                status: "complete",
                statusText: "extracted successfully",
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

  const handleCopyJson = () => {
    if (!activeItem?.result) return;
    navigator.clipboard.writeText(JSON.stringify(activeItem.result, null, 2));
    toast.success("JSON copied to clipboard!");
  };

  const downloadCsv = () => {
    if (!activeItem?.result?.extracted_records) return;
    
    const records = activeItem.result.extracted_records;
    if (records.length === 0) return;
    
    const headers = Object.keys(records[0]).join(",");
    const rows = records.map((r: any) => 
      Object.values(r).map(val => `"${val}"`).join(",")
    ).join("\n");
    
    const csvContent = headers + "\n" + rows;
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `payroll_extraction_${activeItem.primaryName}.csv`;
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto flex flex-col min-h-[calc(100vh-80px)]">
      {/* Header Banner */}
      <PageHeader
        icon={FileCheck}
        title="Payroll Register Extraction"
        description="Automated Payroll Data Extraction & Structuring Engine"
      />

      {/* Drag & Drop Upload Hub */}
      <Panel>
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
          <Button size="sm" className="mt-1 bg-blue-600 text-white hover:bg-blue-700">
            <UploadCloud className="w-4 h-4 mr-2" /> Select Files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => handleFilesAdded(e.target.files)}
          />
        </div>
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
        {/* Left Column: Document Queue */}
        <div className="flex flex-col gap-6">
          <Panel
            title={`Document Queue (${queue.length})`}
            description="Expand items to view detailed processing checklist stages"
            className="flex-1 overflow-hidden flex flex-col"
          >
            <div className="flex-1 overflow-y-auto space-y-3 pr-1 pb-4">
              {queue.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-xs opacity-60">
                  <AlertCircle className="w-8 h-8 mb-2" />
                  Upload files or scan a watched folder to get started.
                </div>
              ) : (
                queue.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-lg border bg-card/40 transition-colors ${
                      activeItemId === item.id ? "ring-2 ring-primary/50 border-primary" : "hover:border-primary/30"
                    }`}
                  >
                    <div
                      className="flex items-center gap-3 p-3 cursor-pointer"
                      onClick={() => setActiveItemId(item.id)}
                    >
                      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                        <FileText className="w-4 h-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{item.displayName}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {item.files.length} file(s) • {item.size}
                        </div>
                      </div>
                      {item.status === "processing" ? (
                        <Loader2 className="w-4 h-4 text-primary animate-spin" />
                      ) : item.status === "complete" ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      ) : item.status === "error" ? (
                        <AlertCircle className="w-4 h-4 text-red-500" />
                      ) : (
                        <Clock className="w-4 h-4 text-muted-foreground" />
                      )}
                    </div>
                    {/* Progress Bar overlay */}
                    {item.status === "processing" && (
                      <div className="h-1 bg-primary/20 w-full overflow-hidden rounded-b-lg">
                        <div 
                          className="h-full bg-primary transition-all duration-300"
                          style={{ width: `${(item.stageIdx / (STEPPER_STAGES.length - 1)) * 100}%` }}
                        />
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
            {/* Execute Bar */}
            {activeItem && activeItem.status !== "complete" && (
              <div className="pt-3 border-t mt-auto shrink-0 flex items-center justify-between">
                 <div className="text-xs text-muted-foreground truncate mr-2">
                   {activeItem.status === "processing" ? activeItem.statusText : "Ready"}
                 </div>
                 <Button
                   size="sm"
                   onClick={processQueue}
                   disabled={isProcessing}
                   className="bg-primary text-primary-foreground text-xs"
                 >
                   {isProcessing ? (
                     <><Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> Processing</>
                   ) : (
                     "Process File"
                   )}
                 </Button>
              </div>
            )}
          </Panel>
        </div>

        {/* Right Column: Extraction Results */}
        <div className="lg:col-span-2 flex flex-col h-[600px]">
          <Panel
            title="Extraction Results"
            description="Detailed parsed data grid, insurance summary, and JSON files for the selected document"
            className="flex-1 flex flex-col min-h-0"
            actions={
              activeItem?.result && (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="text-xs gap-1.5" onClick={handleCopyJson}>
                    <Copy className="w-3.5 h-3.5" /> JSON
                  </Button>
                  <Button size="sm" variant="outline" className="text-xs gap-1.5" onClick={downloadCsv}>
                    <Download className="w-3.5 h-3.5" /> CSV
                  </Button>
                </div>
              )
            }
          >
            {!activeItem?.result ? (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-xs opacity-60 flex-1">
                <FileJson className="w-12 h-12 mb-4 opacity-30" />
                Select a processed document from the queue to view details
              </div>
            ) : (
              <Tabs value={viewMode} onValueChange={(v) => setViewMode(v as any)} className="w-full flex flex-col flex-1 h-full">
                <TabsList className="grid grid-cols-2 mb-4 shrink-0">
                  <TabsTrigger value="table" className="text-xs">
                    <Table className="w-3.5 h-3.5 mr-1.5" /> Data Grid
                  </TabsTrigger>
                  <TabsTrigger value="json" className="text-xs">
                    <Code className="w-3.5 h-3.5 mr-1.5" /> Raw JSON Schema
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="table" className="flex-1 flex flex-col h-full min-h-0 m-0">
                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-2 gap-3 mb-4 shrink-0">
                    <div className="p-3 rounded-lg border bg-card/40 space-y-1">
                      <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                        Total Employees Found
                      </div>
                      <div className="text-sm font-semibold truncate">
                        {activeItem.result?.summary?.total_employees_found || 0}
                      </div>
                    </div>
                    <div className="p-3 rounded-lg border bg-card/40 space-y-1">
                      <div className="text-[10px] text-muted-foreground uppercase font-semibold">
                        Total Check Amount
                      </div>
                      <div className="text-sm font-semibold truncate">
                        ${activeItem.result?.summary?.total_check_amount?.toLocaleString() || "0.00"}
                      </div>
                    </div>
                  </div>

                  {/* Grid / Table */}
                  <div className="flex-1 rounded-lg border bg-card/30 overflow-auto min-h-0">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-muted/50 sticky top-0">
                        <tr>
                          {activeItem.result?.extracted_records?.[0] ? Object.keys(activeItem.result.extracted_records[0]).map(k => (
                             <th key={k} className="p-2 font-semibold border-b whitespace-nowrap">{k}</th>
                          )) : <th className="p-2">No records</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {activeItem.result?.extracted_records?.map((rec: any, i: number) => (
                          <tr key={i} className="border-b hover:bg-muted/20">
                            {Object.values(rec).map((val: any, j: number) => (
                              <td key={j} className="p-2 whitespace-nowrap truncate max-w-[150px]" title={val}>{val}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </TabsContent>

                <TabsContent value="json" className="flex-1 flex flex-col h-full min-h-0 m-0">
                  <div className="flex-1 overflow-auto rounded-lg border bg-background/90 p-4">
                    <pre className="text-xs font-mono text-foreground">
                      {JSON.stringify(activeItem.result, null, 2)}
                    </pre>
                  </div>
                </TabsContent>
              </Tabs>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
