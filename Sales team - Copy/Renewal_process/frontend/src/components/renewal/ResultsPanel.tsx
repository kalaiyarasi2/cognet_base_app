import { FileSpreadsheet, FileText, CheckCircle2, AlertCircle } from "lucide-react";

type Props = {
  status: "idle" | "pending" | "processing" | "success" | "failed";
  invoiceName?: string | null;
  invoiceSize?: number | null;
  censusName?: string | null;
  censusSize?: number | null;
  completedAt: Date | null;
  downloadUrl?: string | null;
  ratesJsonUrl?: string | null;
  error?: string | null;
};

function formatSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function ResultsPanel({
  status,
  invoiceName,
  invoiceSize,
  censusName,
  censusSize,
  completedAt,
  downloadUrl,
  ratesJsonUrl,
  error,
}: Props) {
  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
          <FileText className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-foreground">
            Renewal Results
          </h2>
          <p className="text-sm text-muted-foreground">
            Structured renewal summary ready for review and export.
          </p>
        </div>
      </div>

      {status !== "success" && status !== "failed" ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/40 px-6 py-14 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-card text-muted-foreground shadow-sm">
            <FileText className="h-5 w-5" />
          </div>
          <p className="text-sm font-medium text-foreground">
            {status === "processing" || status === "pending" ? "Processing renewal..." : "No renewal processed yet"}
          </p>
          <p className="mt-1 max-w-sm text-xs text-muted-foreground">
            {status === "processing" || status === "pending"
              ? "The pipeline is matching census rows and extracting rates. Real-time updates are shown in the sidebar."
              : "Upload the renewal invoice and census file, then run the pipeline to populate structured results here."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {status === "success" ? (
            <div className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-foreground">
              <CheckCircle2 className="h-5 w-5 text-success flex-shrink-0" />
              <span className="font-medium">Renewal processed successfully</span>
              {completedAt && (
                <span className="ml-auto text-xs text-muted-foreground">
                  {completedAt.toLocaleString()}
                </span>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive-foreground dark:text-rose-300">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
                <span className="font-semibold">Renewal processing failed</span>
                {completedAt && (
                  <span className="ml-auto text-xs text-muted-foreground">
                    {completedAt.toLocaleString()}
                  </span>
                )}
              </div>
              {error && (
                <p className="mt-1 text-xs font-mono break-words bg-black/10 dark:bg-black/30 p-2 rounded">
                  {error}
                </p>
              )}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <SummaryItem
              icon={<FileText className="h-4 w-4" />}
              label="Renewal Invoice"
              name={invoiceName}
              size={invoiceSize}
            />
            <SummaryItem
              icon={<FileSpreadsheet className="h-4 w-4" />}
              label="Census File"
              name={censusName}
              size={censusSize}
            />
          </div>

          {status === "success" && (downloadUrl || ratesJsonUrl) && (
            <div className="mt-4 flex justify-end gap-3">
              {ratesJsonUrl && (
                <a
                  href={ratesJsonUrl}
                  download
                  className="inline-flex h-9 items-center justify-center rounded-md border border-border bg-background px-4 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  Download Extracted Rates (JSON)
                </a>
              )}
              {downloadUrl && (
                <a
                  href={downloadUrl}
                  download
                  className="inline-flex h-9 items-center justify-center rounded-md bg-brand px-4 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-brand/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  Download Updated Census
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function SummaryItem({
  icon,
  label,
  name,
  size,
}: {
  icon: React.ReactNode;
  label: string;
  name?: string | null;
  size?: number | null;
}) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </div>
      <p className="mt-2 truncate text-sm font-medium text-foreground">
        {name ?? "—"}
      </p>
      {size !== undefined && size !== null && (
        <p className="text-xs text-muted-foreground">{formatSize(size)}</p>
      )}
    </div>
  );
}
