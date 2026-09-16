import type { ReactNode } from "react";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import type { SchemaField } from "./schemaFields";

type Props = {
  field: SchemaField;
  value: unknown;
  error?: string;
  onChange: (value: unknown) => void;
};

function labelFor(field: SchemaField): string {
  return field.required ? `${field.title} *` : field.title;
}

export function WorkflowFieldRenderer({ field, value, error, onChange }: Props) {
  const id = `wf-field-${field.name}`;
  const errId = `${id}-error`;

  let control: ReactNode;
  if (field.kind === "boolean") {
    control = (
      <label className="flex items-center gap-2 text-sm">
        <input
          id={id}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(event) => onChange(event.target.checked)}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errId : undefined}
        />
        <span>{field.title}</span>
      </label>
    );
  } else if (field.kind === "enum" && field.enumValues) {
    control = (
      <select
        id={id}
        className="h-10 w-full rounded border border-border bg-background px-3 text-sm"
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errId : undefined}
      >
        {!field.required ? <option value="">—</option> : null}
        {field.enumValues.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  } else if (field.kind === "textarea" || field.kind === "json") {
    const display =
      field.kind === "json"
        ? typeof value === "string"
          ? value
          : JSON.stringify(value ?? {}, null, 2)
        : String(value ?? "");
    control = (
      <Textarea
        id={id}
        className={field.kind === "json" ? "min-h-24 font-mono text-xs" : "min-h-24"}
        value={display}
        onChange={(event) => {
          if (field.kind === "json") {
            const text = event.target.value;
            try {
              onChange(JSON.parse(text) as unknown);
            } catch {
              onChange(text);
            }
            return;
          }
          onChange(event.target.value);
        }}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errId : undefined}
      />
    );
  } else if (field.kind === "string_array") {
    const display = Array.isArray(value) ? value.join(", ") : String(value ?? "");
    control = (
      <Input
        id={id}
        value={display}
        placeholder="comma or newline separated"
        onChange={(event) =>
          onChange(
            event.target.value
              .split(/[\n,]/)
              .map((s) => s.trim())
              .filter(Boolean),
          )
        }
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errId : undefined}
      />
    );
  } else if (field.kind === "integer" || field.kind === "number") {
    control = (
      <Input
        id={id}
        type="number"
        step={field.kind === "integer" ? 1 : "any"}
        value={value == null || value === "" ? "" : String(value)}
        onChange={(event) => {
          const raw = event.target.value;
          if (raw === "") {
            onChange("");
            return;
          }
          onChange(field.kind === "integer" ? Number.parseInt(raw, 10) : Number.parseFloat(raw));
        }}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errId : undefined}
      />
    );
  } else {
    control = (
      <Input
        id={id}
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errId : undefined}
      />
    );
  }

  return (
    <div className="space-y-1">
      {field.kind === "boolean" ? null : (
        <label htmlFor={id} className="block text-sm text-muted-foreground">
          {labelFor(field)}
        </label>
      )}
      {control}
      {field.description ? (
        <p className="text-[11px] text-muted-foreground">{field.description}</p>
      ) : null}
      {error ? (
        <p id={errId} className="text-xs text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
