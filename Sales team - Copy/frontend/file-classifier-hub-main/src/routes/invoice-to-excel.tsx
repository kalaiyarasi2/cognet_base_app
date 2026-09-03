import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import { 
  FileSpreadsheet, UploadCloud, File, Loader2, X, Download, 
  FileText, CheckCircle2, ChevronRight, AlertCircle, Copy
} from "lucide-react";
import { useAuth } from "@/lib/store";
import { PageHeader } from "@/components/PageHeader";
import { Panel } from "@/components/Panel";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/invoice-to-excel")({
  component: InvoiceToExcelPage,
});

type BatchStatus = "processing" | "complete" | "error";

interface Batch {
  id: string;
  name: string;
  fileCount: number;
  status: BatchStatus;
  records?: any[];
  excelBase64?: string;
  error?: string;
  timestamp: Date;
}

function InvoiceToExcelPage() {
  const { user } = useAuth();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedBatch = batches.find((b) => b.id === selectedBatchId);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(Array.from(e.target.files as FileList));
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const processFiles = async (files: File[]) => {
    if (files.length === 0) return;

    const newBatch: Batch = {
      id: Math.random().toString(36).substring(2, 9),
      name: `Batch ${batches.length + 1}`,
      fileCount: files.length,
      status: "processing",
      timestamp: new Date(),
    };

    setBatches((prev) => [newBatch, ...prev]);
    setSelectedBatchId(newBatch.id);

    const formData = new FormData();
    files.forEach((f) => {
      formData.append("files[]", f);
    });

    try {
      const { getBackendUrl } = await import("@/lib/api");
      const response = await fetch(`${getBackendUrl()}/api/invoice-excel/upload`, {
        method: "POST",
        body: formData,
        headers: {
          "X-Processed-By": user?.email || "SYSTEM"
        }
      });

      if (response.ok) {
        const data = await response.json();
        setBatches((prev) =>
          prev.map((b) =>
            b.id === newBatch.id
              ? {
                  ...b,
                  status: "complete",
                  records: data.records,
                  excelBase64: data.excel_base64,
                }
              : b
          )
        );
        toast.success(`Batch processed successfully.`);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to process invoices");
      }
    } catch (err: any) {
      console.error(err);
      setBatches((prev) =>
        prev.map((b) =>
          b.id === newBatch.id
            ? { ...b, status: "error", error: err.message || "Network error." }
            : b
        )
      );
      toast.error(`Error processing batch: ${err.message}`);
    }
  };

  const handleDownloadExcel = (batch: Batch) => {
    if (!batch.excelBase64) return;
    const link = document.createElement("a");
    link.href = `data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${batch.excelBase64}`;
    link.download = `Astrya_Invoices_${batch.name.replace(/\s+/g, "_")}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 h-full flex flex-col">
      <PageHeader
        title="Invoice to Excel Extractor"
        description="Extract fields directly from vendor payment report PDFs using Vision AI."
        icon={FileSpreadsheet}
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-[600px]">
        {/* Left Panel: Document Queue */}
        <div className="lg:col-span-1 flex flex-col gap-4">
          <Panel className="flex-1 flex flex-col overflow-hidden border-border/60 shadow-sm">
            <div className="p-4 border-b border-border bg-muted/10">
              <h3 className="font-semibold text-sm">Document Queue ({batches.length})</h3>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                History of uploaded batches
              </p>
            </div>
            
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {batches.length === 0 ? (
                <div className="text-center p-6 text-sm text-muted-foreground">
                  No batches processed yet.
                </div>
              ) : (
                batches.map((batch) => (
                  <button
                    key={batch.id}
                    onClick={() => setSelectedBatchId(batch.id)}
                    className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between ${
                      selectedBatchId === batch.id
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-border bg-card hover:bg-muted/30"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-primary shrink-0" />
                        <span className="font-semibold text-sm truncate">{batch.name}</span>
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-1">
                        {batch.fileCount} {batch.fileCount === 1 ? "file" : "files"} • {batch.timestamp.toLocaleTimeString()}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2 pl-2">
                      {batch.status === "processing" && (
                        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 text-[10px] font-semibold">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Processing
                        </span>
                      )}
                      {batch.status === "complete" && (
                        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 text-[10px] font-semibold">
                          <CheckCircle2 className="w-3 h-3" />
                          Complete
                        </span>
                      )}
                      {batch.status === "error" && (
                        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-destructive/10 text-destructive text-[10px] font-semibold">
                          <AlertCircle className="w-3 h-3" />
                          Error
                        </span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          </Panel>
        </div>

        {/* Right Panel: Results & Upload */}
        <div className="lg:col-span-3 flex flex-col gap-6">
          
          {/* Upload Area */}
          <Panel className="p-6 border-border/60 shadow-sm shrink-0">
            <div
              className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center transition-colors ${
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/30 cursor-pointer"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <UploadCloud className="w-10 h-10 text-primary/80 mb-3" />
              <h3 className="text-sm font-semibold mb-1">Drag & Drop Files</h3>
              <p className="text-xs text-muted-foreground mb-4">
                or click to browse • Supports PDF, PNG, JPG
              </p>
              <Button
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                size="sm"
                className="pointer-events-auto"
              >
                Select Files
              </Button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                multiple
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={handleFileChange}
              />
            </div>
          </Panel>

          {/* Results Area */}
          {selectedBatch && (
            <div className="flex-1 flex flex-col gap-4 min-h-0">
              <Panel className="p-4 border-border/60 shadow-sm shrink-0 flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-sm flex items-center gap-2">
                    Results — {selectedBatch.name}
                  </h3>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    Detailed parsed data grid for the selected batch.
                  </p>
                </div>
                
                {selectedBatch.status === "processing" && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Extracting data with AI...
                  </div>
                )}
                
                {selectedBatch.status === "error" && (
                  <div className="flex items-center gap-2 text-sm text-destructive">
                    <AlertCircle className="w-4 h-4" />
                    {selectedBatch.error}
                  </div>
                )}

                {selectedBatch.status === "complete" && selectedBatch.excelBase64 && (
                  <Button 
                    onClick={() => handleDownloadExcel(selectedBatch)}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    <Download className="w-4 h-4" />
                    Download Excel
                  </Button>
                )}
              </Panel>

              {/* Table View */}
              {selectedBatch.status === "complete" && selectedBatch.records && (
                <Panel className="flex-1 flex flex-col overflow-hidden border-border/60 shadow-sm">
                  <div className="border-b border-border bg-muted/10 p-2.5 flex items-center gap-4">
                    <button className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-background border border-border shadow-sm text-xs font-semibold text-foreground">
                      TABLE VIEW
                    </button>
                    <div className="text-[11px] text-muted-foreground ml-auto pr-2">
                      {selectedBatch.records.length} records extracted
                    </div>
                  </div>
                  
                  <div className="flex-1 overflow-auto bg-card">
                    {selectedBatch.records.length === 0 ? (
                      <div className="p-8 text-center text-sm text-muted-foreground">
                        No records were extracted from this batch.
                      </div>
                    ) : (
                      <table className="w-full text-[12px] whitespace-nowrap">
                        <thead className="sticky top-0 bg-muted/50 shadow-sm z-10">
                          <tr>
                            {Object.keys(selectedBatch.records[0] || {}).map((key) => (
                              <th 
                                key={key} 
                                className="px-4 py-3 text-left font-semibold text-muted-foreground uppercase tracking-wider"
                              >
                                {key}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                          {selectedBatch.records.map((record, i) => (
                            <tr key={i} className="hover:bg-muted/20 transition-colors">
                              {Object.values(record).map((val: any, j) => (
                                <td key={j} className="px-4 py-2.5 text-foreground">
                                  {val !== null ? String(val) : <span className="text-muted-foreground italic">null</span>}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </Panel>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
