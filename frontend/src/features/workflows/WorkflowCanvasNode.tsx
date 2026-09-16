import { Handle, Position, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import type { WorkflowNodePort } from "../../api/workflows";
import { categoryGlyph, type WorkflowNodeData } from "./canvasGraph";
import { DEFAULT_HANDLE_ID } from "./portCompatibility";

function portTop(index: number, total: number): string {
  if (total <= 1) return "50%";
  return `${((index + 1) / (total + 1)) * 100}%`;
}

function PortHandles({
  ports,
  type,
  position,
}: {
  ports: WorkflowNodePort[];
  type: "source" | "target";
  position: Position;
}) {
  const list = ports.length > 0 ? ports : [{ name: DEFAULT_HANDLE_ID, data_type: "any" }];
  return (
    <>
      {list.map((port, index) => (
        <Handle
          key={`${type}-${port.name}`}
          id={port.name}
          type={type}
          position={position}
          title={`${port.name}: ${port.data_type}`}
          className="!h-2.5 !w-2.5 !border-background !bg-foreground"
          style={{ top: portTop(index, list.length) }}
        />
      ))}
    </>
  );
}

function statusTone(runStatus: string | null | undefined): string {
  switch ((runStatus ?? "").toUpperCase()) {
    case "SUCCEEDED":
    case "COMPLETED":
      return "ring-1 ring-emerald-500/60";
    case "FAILED":
      return "ring-1 ring-destructive/70";
    case "WAITING":
    case "PAUSED":
      return "ring-1 ring-amber-500/70";
    case "RUNNING":
    case "READY":
      return "ring-1 ring-sky-500/60";
    default:
      return "";
  }
}

function WorkflowCanvasNodeInner({ data, selected }: NodeProps & { data: WorkflowNodeData }) {
  const border = data.unavailable
    ? "border-muted-foreground/40 border-dashed opacity-70"
    : data.invalid
      ? "border-destructive"
      : selected
        ? "border-primary"
        : "border-border";

  return (
    <div
      className={`relative min-w-[180px] rounded border bg-background px-3 py-2 shadow-sm ${border} ${statusTone(
        data.runStatus,
      )}`}
    >
      <PortHandles ports={data.inputPorts} type="target" position={Position.Left} />
      <div className="flex items-start gap-2 pr-1">
        <span
          className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-[11px] text-muted-foreground"
          title={data.category ?? "uncategorized"}
          aria-hidden
        >
          {categoryGlyph(data.category)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-muted-foreground">{data.type}</p>
          <p className="text-sm font-medium leading-tight">{data.label}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {data.unavailable ? (
              <span className="rounded bg-muted px-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                unavailable
              </span>
            ) : null}
            {data.invalid ? (
              <span className="rounded bg-destructive/10 px-1 text-[10px] uppercase tracking-wide text-destructive">
                invalid
              </span>
            ) : null}
            {data.mayPause ? (
              <span className="rounded bg-amber-500/10 px-1 text-[10px] uppercase tracking-wide text-amber-700">
                waiting
              </span>
            ) : null}
            {data.runStatus ? (
              <span className="rounded bg-sky-500/10 px-1 text-[10px] uppercase tracking-wide text-sky-700">
                {data.runStatus}
              </span>
            ) : null}
          </div>
        </div>
      </div>
      <PortHandles ports={data.outputPorts} type="source" position={Position.Right} />
    </div>
  );
}

export const WorkflowCanvasNode = memo(WorkflowCanvasNodeInner);
