import { Handle, Position, useNodeId } from "@xyflow/react";
import { Play, Loader2 } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";

export function StartNode({ data }: { data: any }) {
  const id = useNodeId()!;
  const isRunning = data.isRunning || false;

  return (
    <NodeWrapper id={id}>
      <div style={{
        background: "#fff",
        border: "1.5px solid #e2e8f0",
        borderRadius: 40,
        padding: "10px 24px 10px 10px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
      }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (data.onRun && !isRunning) {
              data.onRun();
            }
          }}
          style={{
            width: 36, height: 36, borderRadius: "50%",
            background: isRunning ? "#fef3c7" : "#dcfce7",
            display: "flex",
            alignItems: "center", justifyContent: "center",
            border: isRunning ? "2px solid #f59e0b" : "2px solid #22c55e",
            cursor: isRunning ? "wait" : "pointer",
            transition: "all 0.2s",
          }}
          title="Run Workflow"
        >
          {isRunning ? (
            <Loader2 style={{ width: 16, height: 16, color: "#f59e0b", animation: "spin 1s linear infinite" }} />
          ) : (
            <Play style={{ width: 14, height: 14, color: "#16a34a", fill: "#16a34a" }} />
          )}
        </button>
        <span style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>Start</span>
        <Handle type="source" position={Position.Right} />
      </div>
    </NodeWrapper>
  );
}
