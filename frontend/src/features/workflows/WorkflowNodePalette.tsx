import type { WorkflowNodeDefinition } from "../../api/workflows";
import { PALETTE_CATEGORIES } from "./canvasGraph";

type Props = {
  catalog: WorkflowNodeDefinition[];
  onAdd: (nodeType: string) => void;
};

function isUnavailable(node: WorkflowNodeDefinition): boolean {
  if (node.executable === false) return true;
  return node.implementation_status === "unavailable";
}

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
              {items.map((node) => {
                const unavailable = isUnavailable(node);
                return (
                  <li key={node.type}>
                    <button
                      type="button"
                      disabled={unavailable}
                      className={
                        unavailable
                          ? "w-full cursor-not-allowed rounded border border-dashed border-border px-2 py-1.5 text-left text-sm text-muted-foreground opacity-70"
                          : "w-full rounded border border-border px-2 py-1.5 text-left text-sm hover:bg-muted"
                      }
                      onClick={() => {
                        if (!unavailable) onAdd(node.type);
                      }}
                      title={
                        unavailable
                          ? `${node.description || node.display_name} (Coming soon)`
                          : node.description
                      }
                    >
                      <span className="block">{node.display_name}</span>
                      {unavailable ? (
                        <span className="mt-0.5 block text-[11px] uppercase tracking-wide">
                          Coming soon
                        </span>
                      ) : null}
                      {node.implementation_status === "beta" ? (
                        <span className="mt-0.5 block text-[11px] uppercase tracking-wide text-muted-foreground">
                          Beta
                        </span>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
