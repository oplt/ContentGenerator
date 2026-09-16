import type { WorkflowNodeDefinition } from "../../api/workflows";
import { PALETTE_CATEGORIES } from "./canvasGraph";

type Props = {
  catalog: WorkflowNodeDefinition[];
  onAdd: (nodeType: string) => void;
};

export function WorkflowNodePalette({ catalog, onAdd }: Props) {
  return (
    <div className="space-y-4 overflow-y-auto p-1">
      {PALETTE_CATEGORIES.map((category) => {
        const items = catalog.filter((node) => node.category === category.key);
        if (items.length === 0) return null;
        return (
          <div key={category.key}>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {category.label}
            </p>
            <ul className="space-y-1">
              {items.map((node) => (
                <li key={node.type}>
                  <button
                    type="button"
                    className="w-full rounded border border-border px-2 py-1.5 text-left text-sm hover:bg-muted"
                    onClick={() => onAdd(node.type)}
                    title={node.description}
                  >
                    {node.display_name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
