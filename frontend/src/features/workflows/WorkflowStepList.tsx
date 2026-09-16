import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import type { WorkflowGraphNode, WorkflowNodeDefinition } from "../../api/workflows";

type Props = {
  steps: WorkflowGraphNode[];
  selectedStepId: string | null;
  addType: string;
  catalog: WorkflowNodeDefinition[];
  onSelect: (id: string) => void;
  onAddTypeChange: (type: string) => void;
  onAdd: () => void;
  onMove: (id: string, direction: -1 | 1) => void;
  onRemove: (id: string) => void;
};

export function WorkflowStepList({
  steps,
  selectedStepId,
  addType,
  catalog,
  onSelect,
  onAddTypeChange,
  onAdd,
  onMove,
  onRemove,
}: Props) {
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          <span className="mb-1 block text-muted-foreground">Add step</span>
          <select
            className="h-10 rounded border border-border bg-background px-3 text-sm"
            value={addType}
            onChange={(event) => onAddTypeChange(event.target.value)}
          >
            {catalog
              .filter((node) => !node.type.endsWith("_trigger"))
              .filter((node) => node.executable !== false && node.implementation_status !== "unavailable")
              .map((node) => (
                <option key={node.type} value={node.type}>
                  {node.display_name}
                  {node.implementation_status === "beta" ? " (beta)" : ""}
                </option>
              ))}
          </select>
        </label>
        <Button variant="secondary" onClick={onAdd}>
          Add
        </Button>
      </div>
      <ol className="space-y-3">
        {steps.map((step, index) => (
          <li key={step.id}>
            <button
              type="button"
              className={`w-full rounded border p-4 text-left transition-colors ${
                selectedStepId === step.id ? "border-primary bg-muted/40" : "border-border"
              }`}
              onClick={() => onSelect(step.id)}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-muted-foreground">Step {index + 1}</p>
                  <p className="font-medium">{step.type}</p>
                  <p className="text-xs text-muted-foreground">{step.id}</p>
                </div>
                <Badge variant="muted">v{step.version}</Badge>
              </div>
            </button>
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => onMove(step.id, -1)}>
                Up
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onMove(step.id, 1)}>
                Down
              </Button>
              <Button size="sm" variant="ghost" onClick={() => onRemove(step.id)}>
                Remove
              </Button>
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}
