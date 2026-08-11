import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { Download, HardDrive, Cloud, Mail, Database, Power, CheckCircle2, FolderOpen, Trash2 } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";
import { useQuery } from "@tanstack/react-query";
import { api, getBackendUrl } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { get, set, del } from "idb-keyval";
import { useState, useEffect } from "react";

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

  const [folderName, setFolderName] = useState<string | null>(null);

  useEffect(() => {
    if (outputType === "local") {
      get(`workflow_dir_${id}`).then((handle: any) => {
        if (handle && handle.name) {
          setFolderName(handle.name);
          updateNodeData(id, { hasLocalFolderHandle: true });
        }
      }).catch(() => {});
    }
  }, [id, outputType, updateNodeData]);

  const handleSelectFolder = async () => {
    try {
      if (typeof window.showDirectoryPicker !== 'function') {
        toast.error("Folder selection is not supported in this browser or requires HTTPS.");
        return;
      }
      // @ts-ignore
      const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
      await set(`workflow_dir_${id}`, dirHandle);
      setFolderName(dirHandle.name);
      updateNodeData(id, { hasLocalFolderHandle: true, savePath: "" });
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        console.error("User cancelled or API not supported", e);
        toast.error("Failed to open folder picker: " + e.message);
      }
    }
  };

  const handleClearFolder = async () => {
    try {
      await del(`workflow_dir_${id}`);
      setFolderName(null);
      updateNodeData(id, { hasLocalFolderHandle: false });
    } catch (e) {
      console.error(e);
    }
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
          <div className="nodrag" style={{ marginTop: 4 }}>
            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 6, marginLeft: 4 }}>
              Save to your PC:
            </div>
            {folderName ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#f8fafc", padding: "6px 10px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
                  <FolderOpen style={{ width: 14, height: 14, color: "#64748b", flexShrink: 0 }} />
                  <span style={{ fontSize: 11, color: "#334155", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: 500 }}>
                    {folderName}
                  </span>
                </div>
                <button
                  onClick={handleClearFolder}
                  style={{ background: "transparent", border: "none", cursor: "pointer", padding: 4, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}
                  title="Remove folder"
                  onMouseEnter={(e) => e.currentTarget.style.color = "#ef4444"}
                  onMouseLeave={(e) => e.currentTarget.style.color = "#94a3b8"}
                >
                  <Trash2 style={{ width: 14, height: 14, color: "inherit" }} />
                </button>
              </div>
            ) : (
              <Button 
                size="sm" 
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation();
                  handleSelectFolder();
                }} 
                style={{ width: "100%", padding: "0 10px", gap: 6, height: 28, fontSize: 11, borderRadius: 6, borderColor: "#e2e8f0", color: "#475569" }} 
              >
                <FolderOpen style={{ width: 12, height: 12 }} /> Choose Folder
              </Button>
            )}
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
