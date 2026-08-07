import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { Bot } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";

interface AgentNodeData {
  label?: string;
  [key: string]: any;
}

export function AgentNode({ data }: { data: AgentNodeData }) {
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
          background: "#dbeafe", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <Bot style={{ width: 14, height: 14, color: "#2563eb" }} />
        </div>
        <div>
          <div style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>
            {data.label || "Agent"}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 11 }}>Agent</div>
        </div>
        <div style={{ position: "absolute", right: 8, top: "35%", transform: "translateY(-50%)", fontSize: 9, color: "#94a3b8", fontWeight: 600 }}>JSON</div>
        <Handle type="source" position={Position.Right} id="json" style={{ top: "35%", background: "#f59e0b" }} />
        
        <div style={{ position: "absolute", right: 8, top: "65%", transform: "translateY(-50%)", fontSize: 9, color: "#94a3b8", fontWeight: 600 }}>Excel</div>
        <Handle type="source" position={Position.Right} id="excel" style={{ top: "65%", background: "#10b981" }} />
      </div>

      {data.options && data.options.length > 0 && (
        <div style={{
          marginTop: 8, background: "#f8fafc", border: "1px solid #e2e8f0",
          borderRadius: 8, padding: "8px 12px", display: "flex", flexDirection: "column", gap: 8
        }}>
          {data.options.map((opt: any) => (
            <div key={opt.name} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={{ fontSize: 11, color: "#64748b", fontWeight: 500 }}>
                {opt.label}
              </label>
              {opt.type === "select" ? (
                <select
                  className="nodrag"
                  value={data[opt.name] || opt.defaultValue || ""}
                  onChange={(e) => updateNodeData(id, { [opt.name]: e.target.value })}
                  style={{
                    fontSize: 12, padding: "4px 8px", borderRadius: 4,
                    border: "1px solid #cbd5e1", background: "#fff", outline: "none"
                  }}
                >
                  <option value="" disabled>Select...</option>
                  {opt.choices?.map((c: string) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              ) : opt.type === "number" ? (
                <input
                  type="number"
                  className="nodrag"
                  value={data[opt.name] || opt.defaultValue || 0}
                  onChange={(e) => updateNodeData(id, { [opt.name]: Number(e.target.value) })}
                  style={{
                    fontSize: 12, padding: "4px 8px", borderRadius: 4,
                    border: "1px solid #cbd5e1", background: "#fff", outline: "none"
                  }}
                />
              ) : (
                <input
                  type="text"
                  className="nodrag"
                  value={data[opt.name] || opt.defaultValue || ""}
                  onChange={(e) => updateNodeData(id, { [opt.name]: e.target.value })}
                  style={{
                    fontSize: 12, padding: "4px 8px", borderRadius: 4,
                    border: "1px solid #cbd5e1", background: "#fff", outline: "none"
                  }}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </NodeWrapper>
  );
}
