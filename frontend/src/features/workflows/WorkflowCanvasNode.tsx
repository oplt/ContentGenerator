import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { WorkflowNodeData } from "./canvasGraph";

function WorkflowCanvasNodeInner({ data, selected }: NodeProps & { data: WorkflowNodeData }) {
  return (
    <div
      className={`min-w-[160px] rounded border bg-background px-3 py-2 shadow-sm ${
        selected ? "border-primary" : "border-border"
      }`}
    >
      <Handle type="target" position={Position.Top} className="!bg-foreground" />
      <p className="text-xs text-muted-foreground">{data.type}</p>
      <p className="text-sm font-medium leading-tight">{data.label}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-foreground" />
    </div>
  );
}

export const WorkflowCanvasNode = memo(WorkflowCanvasNodeInner);
