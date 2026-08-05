import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { FileSpreadsheet } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";

interface PayrollAgentNodeData {
  label?: string;
  [key: string]: any;
}

export function PayrollAgentNode({ data }: { data: PayrollAgentNodeData }) {
  const id = useNodeId()!;
  return (
    <NodeWrapper id={id}>
      <div style={{
        background: "#fff",
        border: "1.5px solid #e2e8f0",
        borderRadius: 40,
        padding: "10px 24px 10px 14px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
      }}>
        <Handle type="target" position={Position.Top} id="custom-target" style={{ background: "#94a3b8" }} />
        <Handle type="target" position={Position.Left} id="left" />
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "#dcfce7", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <FileSpreadsheet style={{ width: 14, height: 14, color: "#16a34a" }} />
        </div>
        <div>
          <div style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>
            {data.label || "Payroll Extractor"}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 11 }}>Agent</div>
        </div>
        <Handle type="source" position={Position.Right} />
      </div>
    </NodeWrapper>
  );
}
