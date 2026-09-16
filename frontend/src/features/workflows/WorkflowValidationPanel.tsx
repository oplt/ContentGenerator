import type { WorkflowCompileError } from "../../api/workflows";

type Props = {
  errors: Array<string | WorkflowCompileError>;
  emptyLabel?: string;
};

export function WorkflowValidationPanel({
  errors,
  emptyLabel = "No validation errors.",
}: Props) {
  if (errors.length === 0) {
    return <p className="mt-2 text-sm text-muted-foreground">{emptyLabel}</p>;
  }
  return (
    <div className="mt-2 space-y-1 text-sm text-destructive" role="status">
      {errors.map((error) => {
        if (typeof error === "string") {
          return <p key={error}>{error}</p>;
        }
        const prefix = [error.code, error.node_id, error.node_type].filter(Boolean).join(" · ");
        return (
          <p key={`${error.code}-${error.node_id}-${error.message}`}>
            {prefix ? `${prefix}: ` : null}
            {error.message}
          </p>
        );
      })}
    </div>
  );
}
