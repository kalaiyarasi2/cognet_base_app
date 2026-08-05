import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { Download, HardDrive, Cloud, Mail, Database, Power, CheckCircle2 } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";
import { useQuery } from "@tanstack/react-query";
import { api, getBackendUrl } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function OutputNode({ data }: { data: any }) {
  const id = useNodeId()!;
  const outputType = data.outputType || "local";

  const profile = useQuery({
    queryKey: ["onedrive-profile"],
    queryFn: api.onedriveProfile,
    enabled: outputType === "onedrive",
    retry: false,
  });

  const handleLogin = () => {
    window.location.href = `${getBackendUrl()}/onedrive/login`;
  };

  const handleLogout = async () => {
    try {
      await fetch(`${getBackendUrl()}/onedrive/logout`, { method: "POST", credentials: "include" });
      profile.refetch();
    } catch (e) {
      console.error("Logout failed:", e);
    }
  };

  const icons: Record<string, any> = {
    local: HardDrive, onedrive: Cloud, email: Mail, database: Database,
  };
  const colors: Record<string, string> = {
    local: "#dcfce7", onedrive: "#dbeafe", email: "#fce7f3", database: "#f3e8ff",
  };
  const iconColors: Record<string, string> = {
    local: "#16a34a", onedrive: "#2563eb", email: "#db2777", database: "#9333ea",
  };

  const Icon = icons[outputType] || Download;
  const { updateNodeData } = useReactFlow();

  const handlePathChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    updateNodeData(id, { savePath: e.target.value });
  };

  return (
    <NodeWrapper id={id}>
      <div style={{
        background: "#fff",
        border: "1.5px solid #e2e8f0",
        borderRadius: outputType === "local" ? 24 : 40,
        padding: "10px 24px 10px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
        minWidth: outputType === "local" || outputType === "onedrive" ? 220 : "auto",
      }}>
        <Handle type="target" position={Position.Left} />
        
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: "50%",
            background: colors[outputType] || "#dcfce7",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Icon style={{ width: 14, height: 14, color: iconColors[outputType] || "#16a34a" }} />
          </div>
          <span style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>
            {data.label || "Output"}
          </span>
        </div>

        {outputType === "local" && (
          <div style={{ marginTop: 4 }}>
            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 4, marginLeft: 4 }}>
              Optional Absolute Path:
            </div>
            <input
              type="text"
              placeholder="e.g. C:\Users\Downloads\result.json"
              value={data.savePath || ""}
              onChange={handlePathChange}
              style={{
                width: "100%",
                padding: "6px 10px",
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid #e2e8f0",
                background: "#f8fafc",
                color: "#334155",
                outline: "none",
              }}
              onFocus={(e) => e.target.style.borderColor = "#cbd5e1"}
              onBlur={(e) => e.target.style.borderColor = "#e2e8f0"}
            />
          </div>
        )}

        {outputType === "onedrive" && (
          <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 8 }}>
            {profile.isLoading ? (
              <span style={{ fontSize: 11, color: "#94a3b8" }}>Checking status...</span>
            ) : profile.data?.authenticated ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#eff6ff", padding: "6px 10px", borderRadius: 8, border: "1px solid #bfdbfe" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <CheckCircle2 style={{ width: 14, height: 14, color: "#3b82f6", flexShrink: 0 }} />
                  <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#1e3a8a" }}>Connected</span>
                    <span style={{ fontSize: 10, color: "#3b82f6", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{profile.data.email}</span>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  style={{ background: "transparent", border: "none", cursor: "pointer", padding: 4, display: "flex", alignItems: "center", justifyContent: "center" }}
                  title="Log out"
                  onMouseEnter={(e) => e.currentTarget.style.color = "#ef4444"}
                  onMouseLeave={(e) => e.currentTarget.style.color = "#94a3b8"}
                >
                  <Power style={{ width: 14, height: 14, color: "inherit" }} />
                </button>
              </div>
            ) : (
              <Button size="sm" onClick={handleLogin} style={{ width: "100%", padding: "0 10px", gap: 6, height: 24, fontSize: 10, background: "#3b82f6", color: "#ffffff", borderRadius: 6 }} onMouseEnter={(e) => e.currentTarget.style.background = "#2563eb"} onMouseLeave={(e) => e.currentTarget.style.background = "#3b82f6"}>
                <Power style={{ width: 10, height: 10 }} /> Continue with Microsoft
              </Button>
            )}
          </div>
        )}
      </div>
    </NodeWrapper>
  );
}
