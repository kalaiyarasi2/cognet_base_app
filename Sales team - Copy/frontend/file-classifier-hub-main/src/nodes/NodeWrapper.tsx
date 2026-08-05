import { useReactFlow } from "@xyflow/react";
import { X } from "lucide-react";
import { type ReactNode } from "react";

interface NodeWrapperProps {
  id: string;
  children: ReactNode;
  style?: React.CSSProperties;
}

export function NodeWrapper({ id, children, style }: NodeWrapperProps) {
  const { deleteElements } = useReactFlow();

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    deleteElements({ nodes: [{ id }] });
  };

  return (
    <div
      className="copilot-node-wrapper"
      style={{ position: "relative", ...style }}
    >
      <button
        className="copilot-node-delete"
        onClick={handleDelete}
        title="Remove node"
      >
        <X style={{ width: 12, height: 12 }} />
      </button>
      {children}
    </div>
  );
}
