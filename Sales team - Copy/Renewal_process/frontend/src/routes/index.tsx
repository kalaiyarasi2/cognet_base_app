import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { Sparkles } from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { Button } from "@/components/ui/button";
import { Header } from "@/components/renewal/Header";
import { UploadCard } from "@/components/renewal/UploadCard";
import {
  PipelineProgress,
  type Stage,
} from "@/components/renewal/PipelineProgress";
import { ResultsPanel } from "@/components/renewal/ResultsPanel";
import { JobHistory, type JobSummary } from "@/components/renewal/JobHistory";
import { toast } from "sonner";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Automated Renewal Processing" },
      {
        name: "description",
        content:
          "Upload the renewal invoice and census file to generate a structured renewal summary in seconds.",
      },
      { property: "og:title", content: "Automated Renewal Processing" },
      {
        property: "og:description",
        content:
          "Automated renewal processing — upload invoice and census to extract structured renewal data.",
      },
    ],
  }),
  component: RenewalPage,
});

const getActiveStageFromLogs = (logs: string | null, status: string): number => {
  if (status === "success") return 3;
  if (!logs) return 0;
  if (logs.includes("Phase 4 – Writing renewal") || logs.includes("Phase 5 – Writing audit")) return 3;
  if (logs.includes("Phase 3 – Matching")) return 2;
  if (logs.includes("Phase 2 – Extracting rates")) return 2; // Data matching active once rates are processed
  if (logs.includes("Phase 1 – Ingesting census")) return 1;
  return 0;
};

function RenewalPage() {
  const [invoice, setInvoice] = useState<File | null>(null);
  const [census, setCensus] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Job list & Selection
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState<JobSummary | null>(null);

  const baseStages: Omit<Stage, "state">[] = [
    { title: "Census Ingestion", description: "Ingesting current employee census" },
    { title: "Invoice Ingestion", description: "Extracting renewal rates via LLM/OCR" },
    { title: "Data Matching", description: "Cross-referencing members to plans & tiers" },
    { title: "Renewal Summary", description: "Generating updated census roster" },
  ];

  // Fetch all jobs in the system
  const fetchJobs = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/jobs");
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (err) {
      console.error("Error fetching jobs list:", err);
    }
  };

  // Poll jobs list
  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 2500);
    return () => clearInterval(interval);
  }, []);

  // Poll selected job details
  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJobDetails(null);
      return;
    }

    let active = true;
    let timer: NodeJS.Timeout;

    const fetchSelectedJob = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/jobs/${selectedJobId}`);
        if (res.ok && active) {
          const job = await res.json();
          setSelectedJobDetails(job);
          
          // Poll every second if job is still in progress
          if (job.status === "pending" || job.status === "processing") {
            timer = setTimeout(fetchSelectedJob, 1000);
          }
        }
      } catch (err) {
        console.error("Error fetching selected job details:", err);
        if (active) {
          timer = setTimeout(fetchSelectedJob, 2000);
        }
      }
    };

    fetchSelectedJob();

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [selectedJobId]);

  // Compute stages for the active stepper
  const stages: Stage[] = baseStages.map((s, i) => {
    let state: Stage["state"] = "pending";
    
    if (selectedJobDetails) {
      const activeStage = getActiveStageFromLogs(selectedJobDetails.logs, selectedJobDetails.status);
      if (selectedJobDetails.status === "success") {
        state = "done";
      } else if (selectedJobDetails.status === "failed") {
        if (i < activeStage) state = "done";
        else if (i === activeStage) state = "pending"; // failed or not completed
      } else {
        if (i < activeStage) state = "done";
        else if (i === activeStage) state = "active";
      }
    } else {
      // New Upload flow progress helpers
      if (i === 0 && census) state = "done";
      if (i === 1 && invoice) state = "done";
    }
    
    return { ...s, state };
  });

  const canProcess = invoice && census && !isSubmitting;

  const handleProcess = async () => {
    if (!invoice || !census) return;
    setIsSubmitting(true);

    try {
      const formData = new FormData();
      formData.append("invoice", invoice);
      formData.append("census", census);

      const response = await fetch("http://localhost:8000/api/process", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to start renewal pipeline");
      }

      const data = await response.json();
      
      // Auto-select the newly spawned job
      setSelectedJobId(data.job_id);
      
      // Clear file upload cards
      setInvoice(null);
      setCensus(null);
      
      // Instantly refresh list
      fetchJobs();

      toast.success("Renewal pipeline started", {
        description: "Your files are being processed in the background.",
      });
    } catch (error: any) {
      console.error(error);
      toast.error("Error processing renewal", {
        description: error.message || "An error occurred while contacting the server.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/jobs/${jobId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success("Job record deleted");
        fetchJobs();
        if (selectedJobId === jobId) {
          setSelectedJobId(null);
        }
      } else {
        toast.error("Failed to delete job");
      }
    } catch (err) {
      console.error("Error deleting job:", err);
      toast.error("Error deleting job");
    }
  };

  return (
    <div className="min-h-screen bg-background transition-colors duration-200">
      <div className="mx-auto w-full max-w-[1600px] px-4 sm:px-8 lg:px-12">
        <Header />

        <main className="space-y-6 pb-16">
          {/* Upload panel only shown/enabled when not viewing a run or if selected is reset */}
          <div className="grid gap-6 sm:grid-cols-2">
            <UploadCard
              step={1}
              title="Census File"
              subtitle="Upload the current employee census roster."
              accept=".csv,.xls,.xlsx,.pdf"
              acceptLabel="CSV, Excel & PDF"
              file={census}
              onFile={(f) => {
                setCensus(f);
                setSelectedJobId(null); // Switch to upload view
              }}
            />

            <UploadCard
              step={2}
              title="Renewal Invoice"
              subtitle="Upload the renewal invoice issued by the carrier."
              accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
              acceptLabel="PDF, Word & Images"
              file={invoice}
              onFile={(f) => {
                setInvoice(f);
                setSelectedJobId(null); // Switch to upload view
              }}
            />
          </div>

          <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              {canProcess
                ? "Both files ready. Run the renewal pipeline."
                : "Upload both files to enable processing."}
            </p>
            <div className="flex gap-2">
              <Button
                onClick={handleProcess}
                disabled={!canProcess}
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                {isSubmitting ? "Queueing…" : "Process Renewal"}
              </Button>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <div className="space-y-6 order-2 lg:order-1">
              <ResultsPanel
                status={selectedJobDetails ? selectedJobDetails.status : "idle"}
                invoiceName={selectedJobDetails?.invoice_name}
                invoiceSize={selectedJobDetails?.invoice_size}
                censusName={selectedJobDetails?.census_name}
                censusSize={selectedJobDetails?.census_size}
                completedAt={selectedJobDetails?.completed_at ? new Date(selectedJobDetails.completed_at * 1000) : null}
                downloadUrl={selectedJobDetails?.download_url}
                ratesJsonUrl={selectedJobDetails?.rates_json_url}
                error={selectedJobDetails?.error}
              />
              
              <JobHistory
                jobs={jobs}
                selectedJobId={selectedJobId}
                onSelectJob={setSelectedJobId}
                onDeleteJob={handleDeleteJob}
              />
            </div>

            <div className="order-1 lg:order-2 space-y-6">
              <PipelineProgress stages={stages} />
            </div>
          </div>
        </main>
      </div>
      <Toaster richColors position="top-right" />
    </div>
  );
}
