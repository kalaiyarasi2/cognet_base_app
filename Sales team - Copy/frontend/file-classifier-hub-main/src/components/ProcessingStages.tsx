import { Check, Loader2, Circle, AlertCircle } from "lucide-react";
import { STAGE_ORDER, STAGE_LABELS, type ProcessingStage } from "@/types/extractor";

interface ProcessingStagesProps {
  currentStage: ProcessingStage;
  stageMessage: string;
}

const ProcessingStages = ({ currentStage, stageMessage }: ProcessingStagesProps) => {
  const currentIdx = STAGE_ORDER.indexOf(currentStage);
  const isError = currentStage === "error";

  return (
    <div className="space-y-1.5 pt-1">
      {STAGE_ORDER.map((stage, i) => {
        const isDone = currentIdx > i || currentStage === "complete";
        const isActive = currentIdx === i && !isError;
        const isPending = currentIdx < i && !isError;

        return (
          <div
            key={stage}
            className={`flex items-center gap-2.5 px-2.5 py-1 rounded-md text-[11.5px] transition-all duration-300 ${
              isActive ? "bg-primary/10 font-medium" : ""
            }`}
          >
            <div className="flex-shrink-0">
              {isDone ? (
                <Check className="w-3.5 h-3.5 text-emerald-500 font-bold" />
              ) : isActive ? (
                <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />
              ) : isError && currentIdx === i ? (
                <AlertCircle className="w-3.5 h-3.5 text-red-500" />
              ) : (
                <Circle className="w-3 h-3 text-muted-foreground opacity-40" />
              )}
            </div>
            <span
              className={`${
                isDone
                  ? "text-emerald-600 font-semibold"
                  : isActive
                  ? "text-foreground"
                  : "text-muted-foreground"
              }`}
            >
              {STAGE_LABELS[stage]}
            </span>
            {isActive && stageMessage && (
              <span className="text-[10px] text-muted-foreground ml-auto truncate max-w-[150px]">
                {stageMessage}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default ProcessingStages;
