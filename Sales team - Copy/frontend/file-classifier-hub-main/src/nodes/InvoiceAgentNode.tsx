import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { Bot } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";

export function InvoiceAgentNode({ data }: { data: any }) {
  const id = useNodeId()!;
  const { updateNodeData } = useReactFlow();
  return (
    <NodeWrapper id={id}>
      <div style={{
        background: "#fff",
        border: "1.5px solid #e2e8f0",
        borderRadius: 40,
        padding: "10px 36px 10px 14px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
      }}>
        <Handle type="target" position={Position.Top} id="custom-target" style={{ background: "#94a3b8" }} />
        <Handle type="target" position={Position.Left} id="left" />
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "#fef3c7", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <Bot style={{ width: 14, height: 14, color: "#d97706" }} />
        </div>
        <div>
          <div style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>Data extraction</div>
          <div style={{ color: "#94a3b8", fontSize: 11 }}>Agent</div>
        </div>
        <Handle type="source" position={Position.Right} id="output" style={{ top: "50%", background: "#3b82f6" }} />
      </div>
      
      <div className="nodrag" style={{ background: "#fff", borderLeft: "1.5px solid #e2e8f0", borderRight: "1.5px solid #e2e8f0", borderBottom: "1.5px solid #e2e8f0", borderBottomLeftRadius: 16, borderBottomRightRadius: 16, padding: "10px 14px", marginTop: -16, paddingTop: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontSize: 10, color: "#64748b", fontWeight: 600 }}>Download Format</label>
          <select 
            value={data.outputFormat || "Both"}
            onChange={(e) => updateNodeData(id, { outputFormat: e.target.value })}
            style={{ fontSize: 11, padding: "4px 8px", borderRadius: 4, border: "1px solid #cbd5e1", outline: "none", color: "#334155", background: "#f8fafc" }}
          >
            <option value="Both">Both (JSON & Excel)</option>
            <option value="JSON">JSON Only</option>
            <option value="Excel">Excel Only</option>
          </select>
        </div>
      </div>
    </NodeWrapper>
  );
}
