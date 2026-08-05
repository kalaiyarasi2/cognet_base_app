import { Handle, Position, useNodeId, useReactFlow } from "@xyflow/react";
import { Upload, FileText, Link2, FolderTree } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";
import { useRef, useState } from "react";

export function InputNode({ data }: { data: any }) {
  const id = useNodeId()!;
  const inputType = data.inputType || "file";
  const iconMap: Record<string, any> = { file: Upload, url: Link2, text: FileText, folder: FolderTree };
  const Icon = iconMap[inputType] || Upload;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const { updateNodeData } = useReactFlow();

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement | HTMLInputElement>) => {
    updateNodeData(id, { content: e.target.value });
  };

  const handleClick = () => {
    if (inputType === "file" && fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFileName(file.name);
      if (data.onFileSelect) {
        data.onFileSelect(file, id);
      }
    }
  };

  return (
    <NodeWrapper id={id}>
      <div 
        onClick={handleClick}
        style={{
          background: "#fff",
          border: "1.5px solid #e2e8f0",
          borderRadius: 40,
          padding: "10px 24px 10px 14px",
          display: "flex",
          alignItems: "center",
          gap: 10,
          boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
          cursor: inputType === "file" ? "pointer" : "default",
          transition: "background 0.2s",
        }}
        onMouseEnter={(e) => { if(inputType === "file") e.currentTarget.style.background = "#f8fafc"; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "#fff"; }}
      >
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "#f3e8ff", display: "flex",
          alignItems: "center", justifyContent: "center",
        }}>
          <Icon style={{ width: 14, height: 14, color: "#9333ea" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", flex: 1, minWidth: 0 }}>
          {inputType === "text" ? (
            <textarea
              className="nodrag"
              placeholder="Enter your note here..."
              value={data.content || ""}
              onChange={handleTextChange}
              style={{
                border: "none", outline: "none", resize: "none",
                background: "transparent", fontSize: 13, color: "#1e293b",
                minHeight: 40, width: 150, fontFamily: "inherit"
              }}
            />
          ) : inputType === "url" || inputType === "folder" ? (
            <input
              className="nodrag"
              type="text"
              placeholder={inputType === "folder" ? "Enter folder path..." : "Enter URL here..."}
              value={data.content || ""}
              onChange={handleTextChange}
              style={{
                border: "none", outline: "none", background: "transparent",
                fontSize: 13, color: "#1e293b", width: 150, padding: "4px 0"
              }}
            />
          ) : (
            <>
              <span style={{ color: "#1e293b", fontWeight: 600, fontSize: 14 }}>
                {data.label || "File Input"}
              </span>
              {fileName && (
                <span style={{ color: "#9333ea", fontSize: 11, maxWidth: 100, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {fileName}
                </span>
              )}
            </>
          )}
        </div>
        <Handle type="target" position={Position.Left} />
        <Handle type="source" position={Position.Right} />
        
        {inputType === "file" && (
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            style={{ display: "none" }} 
          />
        )}
      </div>
    </NodeWrapper>
  );
}

