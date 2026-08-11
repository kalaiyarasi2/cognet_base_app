import { Handle, Position, useNodeId } from "@xyflow/react";
import { Settings } from "lucide-react";
import { NodeWrapper } from "./NodeWrapper";
import { useCustomAgentStore } from "../store/customAgentStore";

export function CustomAgentNode({ data }: { data: any }) {
  const id = useNodeId()!;
  const openDrawer = useCustomAgentStore((state) => state.openDrawer);
  
  const customFields = data.customFields || [];
  const fieldCount = customFields.length;

  return (
    <NodeWrapper id={id}>
      <div className="bg-white border-2 border-blue-200 rounded-xl p-4 w-64 shadow-sm flex flex-col gap-3">
        {/* Removed misleading target handle */}
        
        <div className="flex items-center gap-3 pb-2 border-b border-gray-100">
          <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center shadow-inner">
            <Settings className="w-5 h-5 text-blue-600" />
          </div>
          <div>
            <div className="text-slate-800 font-semibold text-sm">Custom Agent</div>
            <div className="text-slate-400 text-xs">Schema Extension</div>
          </div>
        </div>

        <button
          onClick={() => openDrawer(id, customFields)}
          className="flex items-center justify-center gap-2 w-full py-2.5 bg-gray-50 border border-gray-200 hover:border-blue-300 hover:bg-blue-50 text-slate-700 rounded-lg text-xs font-medium transition-colors nodrag"
        >
          <Settings className="w-3.5 h-3.5" />
          Configure Fields ({fieldCount})
        </button>

        {/* Removed misleading source handles for JSON/Excel as this is a global configuration node */}
      </div>
    </NodeWrapper>
  );
}
