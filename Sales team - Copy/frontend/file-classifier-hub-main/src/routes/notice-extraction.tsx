import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import { FileText, Play, RotateCcw, Download, Zap, AlertCircle, History, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { PdfDropzone } from "@/components/PdfDropzone";
import { useApp } from "@/lib/store";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/notice-extraction")({
  component: NoticeExtractionPage,
});

interface ExtractedData {
  [key: string]: string | number | null | undefined;
}

interface ExtractionResult {
  id: string;
  status: string;
  timestamp: Date;
  document: {
    file_name: string;
    total_pages: number;
    total_lines: number;
    average_confidence: number;
  };
  extracted_data: ExtractedData;
}

function NoticeExtractionPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [isComplete, setIsComplete] = useState(false);
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ExtractionResult[]>([]);
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  const user = useApp((s) => s.user);
  const addLog = useApp((s) => s.addLog);

  async function run() {
    if (!file || isProcessing) return;
    setIsProcessing(true);
    setIsComplete(false);
    setResult(null);
    setError(null);
    setProgress(10);

    let currentProgress = 10;
    progressTimerRef.current = setInterval(() => {
      currentProgress = Math.min(currentProgress + 5, 85);
      setProgress(currentProgress);
    }, 600);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const headers = new Headers();
      if (user?.email) {
        headers.append("X-Processed-By", user.email);
      }

      const { getBackendUrl } = await import("@/lib/api");
      const response = await fetch(`${getBackendUrl()}/api/notice-extraction/api/extract`, {
        method: "POST",
        body: formData,
        headers,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errorData.detail ?? `Server error: ${response.status}`);
      }

      const data: ExtractionResult = await response.json();
      data.id = Math.random().toString(36).substring(2, 9);
      data.timestamp = new Date();

      setResult(data);
      setHistory(prev => [data, ...prev]);
      setProgress(100);
      setIsComplete(true);
      toast.success("Notice extracted successfully.");
      addLog("INFO", "notice-extraction", `Extracted notice from ${file.name}`);
    } catch (err: any) {
      setError(err.message || "Failed to process file");
      toast.error(err.message || "Failed to process file");
      addLog("ERROR", "notice-extraction", err.message);
    } finally {
      if (progressTimerRef.current) clearInterval(progressTimerRef.current);
      setIsProcessing(false);
    }
  }

  function reset() {
    setFile(null);
    setResult(null);
    setIsComplete(false);
    setProgress(0);
    setError(null);
  }

  function downloadOutput() {
    if (!result) return;
    const data = result.extracted_data;
    const jsonString = JSON.stringify(data, null, 2);
    
    const blob = new Blob([jsonString], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${result.document.file_name.replace(/\.[^.]+$/, "")}_extracted.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function downloadExcel() {
    if (!result) return;
    try {
      const { getBackendUrl } = await import("@/lib/api");
      const response = await fetch(`${getBackendUrl()}/api/notice-extraction/api/export-excel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          extracted_data: result.extracted_data,
          file_name: result.document.file_name
        }),
      });

      if (!response.ok) throw new Error("Failed to generate Excel");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${result.document.file_name.replace(/\.[^.]+$/, "")}_extraction_tracker.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("Excel downloaded successfully.");
    } catch (err: any) {
      toast.error(err.message || "Failed to download Excel");
    }
  }

  function loadHistoryItem(item: ExtractionResult) {
    setResult(item);
    setFile(null);
    setIsComplete(true);
    setProgress(100);
    setError(null);
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 h-full flex flex-col">
      <PageHeader
        icon={FileText}
        title="Notice Extraction"
        description="Upload a document, process it, and download a clean notice extraction."
      />
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="flex flex-col gap-3">
          <Panel title="Input" description="Notice document upload">
            <PdfDropzone 
              file={file} 
              onFiles={(fs) => { 
                setFile(fs[0]); 
                setResult(null);
                setIsComplete(false);
                setProgress(0);
                setError(null);
              }} 
            />
            
            {error && (
              <div className="mt-4 flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="mt-4">
              <div className="flex items-center justify-between text-[11.5px] font-medium text-muted-foreground mb-1.5">
                <span>Progress</span>
                <span>{progress}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            <div className="mt-4 flex gap-2 justify-end">
              <Button size="sm" variant="outline" onClick={reset}>
                <RotateCcw className="w-3.5 h-3.5" /> Reset
              </Button>
              <Button size="sm" onClick={run} disabled={!file || isProcessing}>
                {isProcessing ? (
                  <>
                    <Zap className="w-3.5 h-3.5 animate-pulse" /> Processing...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" /> Extract
                  </>
                )}
              </Button>
            </div>
          </Panel>

          <Panel title="History" description="Previously processed files">
            <div className="flex-1 overflow-y-auto min-h-[200px] max-h-[300px] pr-1 space-y-2">
              {history.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-50 py-8">
                  <History className="w-8 h-8 mb-2" />
                  <span className="text-xs">No history yet</span>
                </div>
              ) : (
                history.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => loadHistoryItem(item)}
                    className={cn(
                      "w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between",
                      result?.id === item.id
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-border bg-card hover:bg-muted/30"
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <FileText className={cn("w-3.5 h-3.5 shrink-0", result?.id === item.id ? "text-primary" : "text-muted-foreground")} />
                        <span className="font-semibold text-sm truncate text-foreground">{item.document.file_name}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-1 ml-5">
                        {item.timestamp.toLocaleTimeString()}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground/50" />
                  </button>
                ))
              )}
            </div>
          </Panel>
        </div>

        <Panel
          title="Output"
          description="Extracted notice details"
          actions={
            result && (
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={downloadOutput}>
                  <Download className="w-3 h-3 mr-1" /> JSON
                </Button>
                <Button size="sm" variant="outline" onClick={downloadExcel} className="bg-green-50 text-green-700 hover:bg-green-100 border-green-200">
                  <Download className="w-3 h-3 mr-1" /> Excel
                </Button>
              </div>
            )
          }
        >
          {!result ? (
            <div className="text-[12.5px] text-muted-foreground text-center py-10 flex flex-col items-center">
              <FileText className="w-10 h-10 mb-3 opacity-20" />
              Run extraction to see parsed fields here.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-2 text-[11.5px]">
                <Stat label="File Name" value={result.document.file_name} />
                <Stat label="Total Pages" value={String(result.document.total_pages)} />
                <Stat label="Confidence" value={`${(result.document.average_confidence * 100).toFixed(1)}%`} />
              </div>
              <pre className="text-[11.5px] font-mono whitespace-pre-wrap bg-muted/40 rounded-md p-3 max-h-[500px] overflow-auto leading-relaxed border border-border/50">
                {JSON.stringify(result.extracted_data, null, 2)}
              </pre>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-muted/40 rounded-md p-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-[13px] font-semibold capitalize truncate" title={value}>{value}</div>
    </div>
  );
}
