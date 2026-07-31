import { Check, Loader2, Activity } from "lucide-react";

export type StageState = "pending" | "active" | "done";

export type Stage = {
  title: string;
  description: string;
  state: StageState;
};

export function PipelineProgress({ stages }: { stages: Stage[] }) {
  return (
    <aside className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft text-brand">
          <Activity className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base font-semibold text-foreground">
            Renewal Pipeline
          </h2>
          <p className="text-sm text-muted-foreground">Live progress</p>
        </div>
      </div>

      <ol className="space-y-4">
        {stages.map((stage, i) => (
          <li key={stage.title} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full border-2 text-xs font-medium ${
                  stage.state === "done"
                    ? "border-success bg-success text-background"
                    : stage.state === "active"
                      ? "border-brand bg-brand text-primary-foreground"
                      : "border-border bg-card text-muted-foreground"
                }`}
              >
                {stage.state === "done" ? (
                  <Check className="h-3.5 w-3.5" />
                ) : stage.state === "active" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  i + 1
                )}
              </span>
              {i < stages.length - 1 && (
                <span
                  className={`mt-1 h-8 w-px ${
                    stage.state === "done" ? "bg-success" : "bg-border"
                  }`}
                />
              )}
            </div>
            <div className="pb-2">
              <p
                className={`text-sm font-medium ${
                  stage.state === "pending"
                    ? "text-muted-foreground"
                    : "text-foreground"
                }`}
              >
                {stage.title}
              </p>
              <p className="text-xs text-muted-foreground">
                {stage.description}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  );
}
