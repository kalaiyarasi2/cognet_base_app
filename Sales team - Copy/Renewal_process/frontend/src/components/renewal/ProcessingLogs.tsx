import { useState, useRef, useEffect } from "react";
import { Terminal, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

type Props = {
  logs: string;
};

export function ProcessingLogs({ logs }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const consoleEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen && consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [isOpen, logs]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(logs);
      setCopied(true);
      toast.success("Logs copied", {
        description: "Terminal logs copied to clipboard.",
      });
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      toast.error("Failed to copy", {
        description: "Could not copy logs to clipboard.",
      });
    }
  };

  const parseLogLine = (line: string, index: number) => {
    // Determine log line color based on severity tags
    let textColor = "text-muted-foreground";
    let highlightClass = "";

    if (line.includes("[INFO]")) {
      textColor = "text-success-foreground dark:text-emerald-400";
      if (line.includes("Phase")) {
        highlightClass = "font-semibold text-brand dark:text-sky-400";
      }
    } else if (line.includes("[WARNING]")) {
      textColor = "text-warning dark:text-amber-400 font-medium";
    } else if (line.includes("[ERROR]") || line.includes("Exception:") || line.includes("Error running pipeline")) {
      textColor = "text-destructive dark:text-rose-400 font-semibold";
    } else if (line.includes("MATCH")) {
      textColor = "text-foreground font-medium";
    }

    return (
      <div 
        key={index} 
        className={`py-0.5 px-2 font-mono text-xs leading-relaxed transition-colors hover:bg-muted/40 ${textColor} ${highlightClass}`}
      >
        <span className="select-none opacity-30 mr-2 text-right inline-block w-6">
          {index + 1}
        </span>
        {line}
      </div>
    );
  };

  const lines = logs.split("\n").filter((l) => l.trim() !== "");

  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      {/* Header Accordion Trigger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between p-4 text-left transition-colors hover:bg-muted/30 focus-visible:outline-none"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Terminal className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">
              Technical Execution Logs
            </h3>
            <p className="text-xs text-muted-foreground">
              {lines.length} lines of backend processing events
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isOpen && (
            <Button
              size="icon"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                handleCopy();
              }}
              className="h-8 w-8 hover:bg-muted text-muted-foreground hover:text-foreground"
              title="Copy all logs"
            >
              {copied ? (
                <Check className="h-4 w-4 text-success" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          )}
          <div className="text-muted-foreground">
            {isOpen ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </div>
        </div>
      </button>

      {/* Expanded Console Logs */}
      {isOpen && (
        <div className="border-t border-border bg-slate-950 dark:bg-black/80 p-3 max-h-[350px] overflow-y-auto select-text scrollbar-thin scrollbar-thumb-muted">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/5 text-[10px] uppercase tracking-wider text-muted-foreground select-none font-mono">
            <span>stdout console session</span>
            <span>UTF-8</span>
          </div>
          <div className="space-y-0.5">
            {lines.map((line, idx) => parseLogLine(line, idx))}
            <div ref={consoleEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}
