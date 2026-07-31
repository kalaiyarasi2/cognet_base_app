import { Clock, CheckCircle2, XCircle, AlertCircle, Trash2, ListRestart } from "lucide-react";
import { Button } from "@/components/ui/button";

export type JobSummary = {
  job_id: string;
  status: "pending" | "processing" | "success" | "failed";
  invoice_name: string;
  census_name: string;
  invoice_size: number;
  census_size: number;
  created_at: number;
  completed_at: number | null;
  download_url: string | null;
  error: string | null;
  log_length: number;
};

type Props = {
  jobs: JobSummary[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string | null) => void;
  onDeleteJob: (jobId: string) => void;
};

export function JobHistory({ jobs, selectedJobId, onSelectJob, onDeleteJob }: Props) {
  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-sm flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
            <ListRestart className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-foreground">
              Processing History
            </h2>
            <p className="text-xs text-muted-foreground">Recent runs in system</p>
          </div>
        </div>
        {selectedJobId && (
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => onSelectJob(null)}
            className="text-xs h-7 px-2 hover:bg-muted"
          >
            New Upload
          </Button>
        )}
      </div>

      {jobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border p-8 text-center bg-muted/20">
          <p className="text-xs font-medium text-muted-foreground">No processing history found.</p>
          <p className="text-[10px] text-muted-foreground mt-1">Upload files above to start a run.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[350px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-muted">
          {jobs.map((job, index) => {
            const isSelected = job.job_id === selectedJobId;
            // Oldest job gets Run #1, latest gets Run #N
            const runNumber = jobs.length - index;

            return (
              <div
                key={job.job_id}
                onClick={() => onSelectJob(job.job_id)}
                className={`group relative flex flex-col gap-2 rounded-lg border p-3 text-left transition-all duration-200 cursor-pointer ${
                  isSelected
                    ? "border-brand bg-brand-soft/20 ring-1 ring-brand/30"
                    : "border-border bg-muted/10 hover:border-border-hover hover:bg-muted/30"
                }`}
              >
                {/* Header info */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-foreground">
                      Run #{runNumber}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {formatDate(job.created_at)} at {formatTime(job.created_at)}
                    </span>
                  </div>
                  
                  {/* Status Badge */}
                  <div className="flex items-center gap-2">
                    {job.status === "success" && (
                      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-success/15 text-success">
                        <CheckCircle2 className="h-3 w-3" />
                        Completed
                      </span>
                    )}
                    {job.status === "failed" && (
                      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-destructive/15 text-destructive dark:text-rose-300">
                        <XCircle className="h-3 w-3" />
                        Failed
                      </span>
                    )}
                    {(job.status === "processing" || job.status === "pending") && (
                      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium bg-brand/15 text-brand animate-pulse">
                        <Clock className="h-3 w-3" />
                        {job.status === "processing" ? "Running" : "Pending"}
                      </span>
                    )}
                    
                    {/* Delete button, visible on hover */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteJob(job.job_id);
                      }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 text-muted-foreground hover:text-destructive rounded hover:bg-background/80"
                      title="Delete run record"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* File details */}
                <div className="text-[11px] space-y-0.5 text-muted-foreground truncate">
                  <p className="truncate">
                    <span className="font-medium text-foreground/75">Census:</span> {job.census_name}
                  </p>
                  <p className="truncate">
                    <span className="font-medium text-foreground/75">Invoice:</span> {job.invoice_name}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
