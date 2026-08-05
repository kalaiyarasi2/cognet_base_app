import { createFileRoute } from "@tanstack/react-router";
import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import {
  ReactFlow,
  Controls,
  ControlButton,
  Background,
  BackgroundVariant,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import "../copilot-flow.css";

import { InputNode } from "../nodes/InputNode";
import { OutputNode } from "../nodes/OutputNode";
import { ClassifierNode } from "../nodes/ClassifierNode";
import { AgentNode } from "../nodes/AgentNode";
import { InvoiceAgentNode } from "../nodes/InvoiceAgentNode";
import { CustomAgentNode } from "../nodes/CustomAgentNode";
import { StartNode } from "../nodes/StartNode";
import { PayrollAgentNode } from "../nodes/PayrollAgentNode";
import { FieldEditorDrawer } from "../components/FieldEditorDrawer";
import { DeletableEdge } from "../edges/DeletableEdge";

import {
  Play, Loader2, Upload, Bot, Tags, Download, FileText, FolderTree,
  Scale, RefreshCw, Cpu, FileCheck, ChevronRight,
  Link2, HardDrive, Cloud, Mail, Database, Square, StickyNote, X, Settings, Lock, Unlock, Trash2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import axios from "axios";

export const Route = createFileRoute("/co-pilot")({
  component: CoPilotPage,
});

/* ── Node type registry ─────────────────────────────────────── */
const nodeTypes = {
  startNode: StartNode,
  inputNode: InputNode,
  classifierNode: ClassifierNode,
  agentNode: AgentNode,
  invoiceAgentNode: InvoiceAgentNode,
  customAgentNode: CustomAgentNode,
  outputNode: OutputNode,
  payrollAgentNode: PayrollAgentNode,
};

const edgeTypes = {
  deletable: DeletableEdge,
};

/* ── Sidebar items ──────────────────────────────────────────── */
const sidebarGroups = [
  {
    label: "Core",
    items: [
      { type: "startNode", label: "Start", icon: Play, data: {} },
      { type: "outputNode", label: "End", icon: Square, data: { label: "End", outputType: "local" } },
      { type: "inputNode", label: "Note", icon: StickyNote, data: { label: "Note", inputType: "text" } },
    ],
  },
  {
    label: "Agents",
    items: [
      { 
        type: "agentNode", label: "Text Extraction", icon: FileText, 
        data: { 
          label: "Text Extraction",
          options: [
            { name: "max_pages", label: "Max Pages", type: "number", defaultValue: 3 },
            { name: "force_ocr", label: "Force OCR", type: "select", choices: ["false", "true"], defaultValue: "false" }
          ]
        } 
      },
      { 
        type: "agentNode", label: "Classification", icon: Tags, 
        data: { 
          label: "Classification",
          options: [
            { name: "llm_model", label: "LLM Model", type: "select", choices: ["gpt-4o", "gpt-3.5-turbo"], defaultValue: "gpt-4o" },
            { name: "threshold", label: "Score Threshold", type: "number", defaultValue: 3 }
          ]
        } 
      },
      { 
        type: "agentNode", label: "File Converter", icon: RefreshCw, 
        data: { 
          label: "File Converter",
          options: [
            { name: "source_format", label: "Source Format", type: "select", choices: ["pdf", "csv", "json", "excel", "xml", "txt"], defaultValue: "pdf" },
            { name: "target_format", label: "Target Format", type: "select", choices: ["txt", "csv", "json", "excel", "xml", "pdf"], defaultValue: "txt" }
          ]
        } 
      },
      { type: "invoiceAgentNode", label: "Data extraction", icon: Bot, data: { label: "Data extraction" } },
      { type: "customAgentNode", label: "Customization Agent", icon: Settings, data: { label: "Customization Agent" } },
      { type: "agentNode", label: "RPVE Agent", icon: Bot, data: { label: "RPVE Agent" } },
      { type: "agentNode", label: "Resourcing Agent", icon: Bot, data: { label: "Resourcing Agent" } },
      { type: "agentNode", label: "Parity Agent", icon: Bot, data: { label: "Parity Agent" } },
      { type: "agentNode", label: "Renewal Agent", icon: Bot, data: { label: "Renewal Agent" } },
      { type: "payrollAgentNode", label: "Payroll Extractor", icon: Bot, data: { label: "Payroll Extractor" } },
    ],
  },
  {
    label: "Tools",
    items: [
      { type: "inputNode", label: "File Upload", icon: Upload, data: { inputType: "file", label: "File Upload" } },
      { type: "inputNode", label: "Folder Upload", icon: FolderTree, data: { inputType: "folder", label: "Folder Upload" } },
      { type: "inputNode", label: "URL Source", icon: Link2, data: { inputType: "url", label: "URL Source" } },
    ],
  },
  {
    label: "Data",
    items: [
      { type: "outputNode", label: "Save Locally", icon: HardDrive, data: { label: "Local Save", outputType: "local" } },
      { type: "outputNode", label: "OneDrive", icon: Cloud, data: { label: "OneDrive", outputType: "onedrive" } },
      { type: "outputNode", label: "Email", icon: Mail, data: { label: "Email", outputType: "email" } },
      { type: "outputNode", label: "Database", icon: Database, data: { label: "Database", outputType: "database" } },
    ],
  },
];

/* ── Default pre-populated workflow ─────────────────────────── */
const defaultNodes: Node[] = [
  { id: "start-1", type: "startNode", position: { x: 250, y: 200 }, data: {} }
];

const defaultEdges: Edge[] = [];

/* ── Unique ID counter ──────────────────────────────────────── */
let nodeIdCounter = 10;
const getNextId = () => `node-${++nodeIdCounter}`;

/* ── Component ──────────────────────────────────────────────── */
export function CoPilotPage() {
  const [nodes, setNodes] = useState<Node[]>(defaultNodes);
  const [edges, setEdges] = useState<Edge[]>(defaultEdges);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [reactFlowInstance, setReactFlowInstance] = useState<any>(null);
  const [isLocked, setIsLocked] = useState(false);

  const [savedWorkflows, setSavedWorkflows] = useState<any[]>([]);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState<string>("New workflow");
  const [isDirty, setIsDirty] = useState<boolean>(false);

  const [uploadedFiles, setUploadedFiles] = useState<Record<string, File>>({});

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds));
      setIsDirty(true);
    },
    []
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      setEdges((eds) => applyEdgeChanges(changes, eds));
      setIsDirty(true);
    },
    []
  );
  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge({ ...params, type: "deletable", style: { stroke: "#cbd5e1", strokeWidth: 1.5 } }, eds)
      );
      setIsDirty(true);
    },
    []
  );

  const onFileSelect = useCallback((file: File, nodeId: string) => {
    setUploadedFiles(prev => ({ ...prev, [nodeId]: file }));
  }, []);

  const onPathChange = useCallback((id: string, savePath: string) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return { ...node, data: { ...node.data, savePath } };
        }
        return node;
      })
    );
  }, []);

  /* ── Drag & Drop ───────────────────────────────────────────── */
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/reactflow");
      if (!raw || !reactFlowInstance) return;

      const { type, data } = JSON.parse(raw);
      const position = reactFlowInstance.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode: Node = { id: getNextId(), type, position, data: { ...data } };
      setNodes((nds) => [...nds, newNode]);
    },
    [reactFlowInstance]
  );

  /* ── Project Persistence ─────────────────────────────────────── */
  const fetchProjects = useCallback(async () => {
    try {
      const response = await axios.get("http://localhost:8000/api/workflow/projects", { withCredentials: true });
      if (Array.isArray(response.data)) {
        setSavedWorkflows(response.data);
      }
    } catch (e) {
      console.error("Failed to fetch projects:", e);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const loadProject = useCallback(async (id: string) => {
    if (isDirty) {
      const confirm = window.confirm("You have unsaved changes. Are you sure you want to load a different project?");
      if (!confirm) return;
    }
    try {
      const response = await axios.get(`http://localhost:8000/api/workflow/projects/${id}`, { withCredentials: true });
      if (response.data.status === "success") {
        setNodes(response.data.project.nodes || []);
        setEdges(response.data.project.edges || []);
        setWorkflowName(response.data.project.name);
        setCurrentWorkflowId(id);
        setIsDirty(false);
      } else {
        toast.error("Failed to load project: " + response.data.message);
      }
    } catch (e) {
      console.error("Failed to load project:", e);
      toast.error("Failed to load project.");
    }
  }, [isDirty]);

  const handleSaveWorkflow = useCallback(async () => {
    let nameToSave = workflowName;
    if (!nameToSave || nameToSave.trim() === "" || nameToSave === "New workflow") {
      const userInput = window.prompt("Enter a name for this workflow:", "My Workflow");
      if (!userInput) return; // User cancelled
      nameToSave = userInput;
      setWorkflowName(nameToSave);
    }

    try {
      const payload = {
        id: currentWorkflowId,
        name: nameToSave,
        nodes: nodes,
        edges: edges
      };
      const response = await axios.post("http://localhost:8000/api/workflow/projects/save", payload, { withCredentials: true });
      if (response.data.status === "success") {
        toast.success("Workflow saved successfully!");
        setCurrentWorkflowId(response.data.id);
        setIsDirty(false);
        fetchProjects();
      } else {
        toast.error("Failed to save: " + response.data.message);
      }
    } catch (e) {
      console.error("Failed to save workflow:", e);
      toast.error("Error saving workflow.");
    }
  }, [currentWorkflowId, workflowName, nodes, edges, fetchProjects]);

  const handleNewWorkflow = useCallback(() => {
    if (isDirty) {
      const confirm = window.confirm("You have unsaved changes. Are you sure you want to start a new project?");
      if (!confirm) return;
    }
    setNodes([{ id: "start-1", type: "startNode", position: { x: 250, y: 200 }, data: {} }]);
    setEdges([]);
    setWorkflowName("New workflow");
    setCurrentWorkflowId(null);
    setIsDirty(false);
  }, [isDirty]);

  const handleDeleteProject = useCallback(async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const confirm = window.confirm("Are you sure you want to delete this workflow?");
    if (!confirm) return;
    try {
      const response = await axios.delete(`http://localhost:8000/api/workflow/projects/${id}`, { withCredentials: true });
      if (response.data.status === "success") {
        toast.success("Workflow deleted.");
        fetchProjects();
        if (currentWorkflowId === id) {
          handleNewWorkflow();
        }
      } else {
        toast.error("Failed to delete workflow.");
      }
    } catch (err) {
      console.error("Delete error", err);
      toast.error("Error deleting workflow.");
    }
  }, [currentWorkflowId, fetchProjects, handleNewWorkflow]);

  /* ── Run workflow ──────────────────────────────────────────── */
  const handleRunWorkflow = useCallback(async () => {
    setIsRunning(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("nodes", JSON.stringify(nodes));
      formData.append("edges", JSON.stringify(edges));
      Object.values(uploadedFiles).forEach((file) => {
        formData.append("files", file);
      });

      const response = await axios.post("http://localhost:8000/api/workflow/run-workflow", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        withCredentials: true
      });
      
      if (response.data.status === "success") {
        toast.success("Workflow completed successfully!");
        setResult(response.data);

        // If the workflow contains a "Local Save" node without an absolute path, automatically trigger a browser download fallback
        const localSaveNode = nodes.find(n => n.type === "outputNode" && (n.data?.outputType === "local" || !n.data?.outputType));
        if (localSaveNode && !localSaveNode.data?.savePath && response.data.simulated_output_data) {
          // 1. Download JSON
          const jsonString = JSON.stringify(response.data.simulated_output_data, null, 2);
          const blob = new Blob([jsonString], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = "workflow_result.json";
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          
          // 2. Download Excel if available
          if (response.data.simulated_output_data.excel) {
             const excelUrl = response.data.simulated_output_data.excel;
             // We can just open the URL in a hidden iframe or create an anchor to trigger the browser download
             const excelLink = document.createElement("a");
             excelLink.href = excelUrl;
             // Ensure it triggers download
             excelLink.setAttribute("download", "");
             excelLink.target = "_blank"; // Fallback
             document.body.appendChild(excelLink);
             excelLink.click();
             document.body.removeChild(excelLink);
          }
        }
      } else {
        toast.error(response.data.message || "Workflow failed");
      }
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "Failed to run workflow");
    } finally {
      setIsRunning(false);
    }
  }, [nodes, edges]);

  /* ── Keep nodes wired to the run handler and path change ───── */
  const nodesWithHandlers = useMemo(() => {
    return nodes.map((node) => {
      let data = { ...node.data };
      if (node.type === "startNode") {
        data = { ...data, onRun: handleRunWorkflow, isRunning };
      }
      if (node.type === "outputNode") {
        data = { ...data, onPathChange };
      }
      if (node.type === "inputNode") {
        data = { ...data, onFileSelect };
      }
      return { ...node, data };
    });
  }, [nodes, handleRunWorkflow, isRunning, onPathChange, onFileSelect]);

  const defaultEdgeOptions = useMemo(
    () => ({ style: { stroke: "#cbd5e1", strokeWidth: 1.5 } }),
    []
  );

  return (
    <div style={{
      display: "flex",
      width: "100%",
      height: "calc(100vh - 130px)",
      borderRadius: 16,
      overflow: "hidden",
      border: "1px solid #e2e8f0",
      background: "#fafaf9",
    }}>
      {/* ── Left Sidebar ─────────────────────────────────────── */}
      <div style={{
        width: 200,
        background: "#fff",
        borderRight: "1px solid #e2e8f0",
        overflowY: "auto",
        flexShrink: 0,
        paddingTop: 8,
      }}>
        {sidebarGroups.map((group) => (
          <div key={group.label} style={{ marginBottom: 4 }}>
            <div style={{
              fontSize: 11,
              fontWeight: 500,
              color: "#94a3b8",
              padding: "12px 20px 6px",
            }}>
              {group.label}
            </div>

            {group.items.map((item, idx) => {
              const Icon = item.icon;
              return (
                <div
                  key={`${item.type}-${idx}`}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(
                      "application/reactflow",
                      JSON.stringify({ type: item.type, data: item.data })
                    );
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={() => {
                    /* Click-to-add: place the node at a visible center position */
                    const position = reactFlowInstance
                      ? reactFlowInstance.screenToFlowPosition({
                          x: window.innerWidth / 2,
                          y: window.innerHeight / 2,
                        })
                      : { x: 300 + Math.random() * 200, y: 150 + Math.random() * 200 };

                    const newNode: Node = {
                      id: getNextId(),
                      type: item.type,
                      position,
                      data: { ...item.data },
                    };
                    setNodes((nds) => [...nds, newNode]);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "7px 20px",
                    cursor: "pointer",
                    transition: "background 0.15s",
                    fontSize: 14,
                    color: "#1e293b",
                    userSelect: "none",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <Icon style={{ width: 16, height: 16, color: "#64748b", flexShrink: 0 }} />
                  <span style={{ whiteSpace: "nowrap" }}>{item.label}</span>
                </div>
              );
            })}
          </div>
        ))}
        {/* Saved Projects */}
        {savedWorkflows.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{
              textTransform: "uppercase", fontSize: 11, fontWeight: 700,
              color: "#94a3b8", padding: "12px 20px 6px",
            }}>
              Saved Projects
            </div>
            {savedWorkflows.map((proj) => (
              <div
                key={proj.id}
                onClick={() => loadProject(proj.id)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "7px 20px", cursor: "pointer", transition: "background 0.15s",
                  fontSize: 14, color: "#1e293b", userSelect: "none",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#eff6ff")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Cloud style={{ width: 14, height: 14, color: "#3b82f6" }} />
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 110 }}>{proj.name}</span>
                </div>
                <div
                  onClick={(e) => handleDeleteProject(proj.id, e)}
                  style={{ padding: 4, borderRadius: 4, cursor: "pointer", display: "flex" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#fee2e2")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  title="Delete Project"
                >
                  <Trash2 style={{ width: 14, height: 14, color: "#ef4444" }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Main Canvas ──────────────────────────────────────── */}
      <div ref={reactFlowWrapper} style={{ flex: 1, position: "relative" }}>
        {/* Top Bar */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, zIndex: 10,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "12px 20px",
          background: "rgba(250,250,249,0.85)",
          backdropFilter: "blur(8px)",
          borderBottom: "1px solid #e2e8f0",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <input
              type="text"
              value={workflowName}
              onChange={(e) => {
                setWorkflowName(e.target.value);
                setIsDirty(true);
              }}
              placeholder="Untitled Workflow"
              style={{
                fontWeight: 700, fontSize: 16, color: "#0f172a",
                background: "transparent", border: "none", outline: "none",
                padding: "2px 0", width: 180
              }}
            />
            {isDirty && (
              <span style={{
                fontSize: 11, color: "#ea580c", background: "#ffedd5",
                padding: "2px 8px", borderRadius: 6, fontWeight: 600
              }}>Unsaved</span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleNewWorkflow}
              style={{ gap: 6, fontSize: 13, color: "#64748b" }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              New
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSaveWorkflow}
              style={{
                gap: 6, borderRadius: 8,
                borderColor: "#e2e8f0", color: "#0f172a",
                fontWeight: 500, fontSize: 13,
              }}
            >
              <HardDrive className="w-3.5 h-3.5" />
              Save
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRunWorkflow}
              disabled={isRunning}
              style={{
                gap: 6, borderRadius: 8,
                borderColor: "#e2e8f0", color: "#0f172a",
                fontWeight: 500, fontSize: 13,
              }}
            >
              {isRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              Preview
            </Button>
            <Button
              size="sm"
              onClick={() => toast.success("Workflow published successfully!")}
              style={{
                gap: 6, borderRadius: 8,
                background: "#0f172a", color: "#fff",
                fontWeight: 600, fontSize: 13,
              }}
            >
              Publish
            </Button>
          </div>
        </div>

        <ReactFlow
          className="copilot-flow"
          nodes={nodesWithHandlers}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setReactFlowInstance}
          onDragOver={onDragOver}
          onDrop={onDrop}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          deleteKeyCode={["Backspace", "Delete"]}
          fitView
          nodesDraggable={!isLocked}
          nodesConnectable={!isLocked}
          elementsSelectable={!isLocked}
          panOnDrag={!isLocked}
          zoomOnScroll={!isLocked}
          panOnScroll={false}
          style={{ background: "#fafaf9" }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#e2e8f0" />
          <Controls
            showInteractive={false}
            style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.06)", overflow: "hidden" }}
          >
            <ControlButton onClick={() => setIsLocked(!isLocked)} title="Lock/Unlock Workspace">
              {isLocked ? <Lock style={{ width: 14, height: 14, color: "#ef4444" }} /> : <Unlock style={{ width: 14, height: 14, color: "#64748b" }} />}
            </ControlButton>
          </Controls>
          <FieldEditorDrawer />
        </ReactFlow>

        {/* ── Result Panel ──────────────────────────────────── */}
        {result && (
          <div style={{
            position: "absolute",
            bottom: 16,
            left: 16,
            zIndex: 10,
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 14,
            padding: 16,
            maxWidth: 380,
            maxHeight: 300,
            overflowY: "auto",
            boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: "50%",
                  background: "#22c55e", boxShadow: "0 0 6px #22c55e",
                }} />
                <span style={{ color: "#0f172a", fontWeight: 600, fontSize: 13 }}>Workflow Result</span>
              </div>
              <button 
                onClick={() => setResult(null)}
                style={{
                  background: "transparent", border: "none", cursor: "pointer",
                  color: "#94a3b8", display: "flex", alignItems: "center", justifyContent: "center"
                }}
                title="Close"
              >
                <X style={{ width: 14, height: 14 }} />
              </button>
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 12 }}>
              {result.execution_log?.map((log: string, i: number) => (
                <div key={i} style={{ marginBottom: 4, display: "flex", gap: 6 }}>
                  <ChevronRight style={{ width: 12, height: 12, color: "#3b82f6", flexShrink: 0, marginTop: 2 }} />
                  <span>{log}</span>
                </div>
              ))}
            </div>
            {result.simulated_output_data && (
              <pre style={{
                fontSize: 11, color: "#334155",
                background: "#f8fafc", padding: 10,
                borderRadius: 8, whiteSpace: "pre-wrap",
                border: "1px solid #e2e8f0",
              }}>
                {result.simulated_output_data.text_full
                  ? result.simulated_output_data.text_full
                  : JSON.stringify(result.simulated_output_data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
