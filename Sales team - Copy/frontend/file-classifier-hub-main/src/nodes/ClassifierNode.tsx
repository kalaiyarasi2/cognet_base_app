import { Handle, Position, useNodeId } from "@xyflow/react";
import { Tags } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";

export function ClassifierNode({ data }: { data: any }) {
  const id = useNodeId()!;
  return (
    <NodeWrapper id={id}>
      <div style={{
        background: "#fff",
        border: "1.5px solid #e2e8f0",
        borderRadius: 16,
        padding: 16,
        minWidth: 200,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
      }}>
        <Handle type="target" position={Position.Left} />

        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: "50%",
            background: "#fef3c7", display: "flex",
            alignItems: "center", justifyContent: "center",
          }}>
            <Tags style={{ width: 14, height: 14, color: "#d97706" }} />
          </div>
          <div style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>
            {data.label || "If / else"}
          </div>
        </div>

        {data.condition && (
          <div style={{
            fontSize: 12, color: "#64748b",
            padding: "8px 10px", background: "#f8fafc",
            borderRadius: 8, border: "1px solid #e2e8f0",
            fontFamily: "monospace",
          }}>
            {data.condition}
          </div>
        )}

        {data.model && (
          <div style={{
            fontSize: 11, color: "#64748b",
            padding: "4px 8px", background: "#f8fafc",
            borderRadius: 6, border: "1px solid #e2e8f0",
            marginTop: 6, display: "inline-block",
          }}>
            {data.model}
          </div>
        )}

        <Handle type="source" position={Position.Right} id="0" style={{ top: "30%" }} />
        <Handle type="source" position={Position.Right} id="1" style={{ top: "55%" }} />
        <Handle type="source" position={Position.Right} id="2" style={{ top: "80%" }} />
      </div>
    </NodeWrapper>
  );
}
