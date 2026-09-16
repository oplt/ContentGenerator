import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import type { WorkflowNodeDefinition } from "../../api/workflows";
import { validateWorkflowNodeConfig } from "../../api/workflows";
import { WorkflowFieldRenderer } from "./WorkflowFieldRenderer";
import {
  coerceFieldValue,
  mapConfigErrorsToFields,
  parseConfigSchema,
  type SchemaField,
} from "./schemaFields";

type Props = {
  nodeType: string;
  version: number;
  definition: WorkflowNodeDefinition | null;
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
};

export function WorkflowNodeConfigForm({
  nodeType,
  version,
  definition,
  config,
  onChange,
}: Props) {
  const fields = useMemo(
    () => parseConfigSchema(definition?.config_schema),
    [definition?.config_schema],
  );
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const debounceRef = useRef<number | null>(null);
  const form = useForm<Record<string, unknown>>({
    defaultValues: config,
    mode: "onChange",
  });

  // Reset when switching nodes or external config snapshot changes identity.
  useEffect(() => {
    form.reset(config);
    setServerErrors({});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset on node identity only
  }, [nodeType, version]);

  useEffect(() => {
    return () => {
      if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
    };
  }, []);

  function scheduleValidate(next: Record<string, unknown>) {
    if (debounceRef.current != null) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void validateWorkflowNodeConfig(nodeType, { version, config: next })
        .then((result) => {
          if (result.valid) {
            setServerErrors({});
            return;
          }
          setServerErrors(
            mapConfigErrorsToFields(
              result.errors,
              fields.map((f) => f.name),
            ),
          );
        })
        .catch((error: Error) => {
          setServerErrors({ _form: error.message });
        });
    }, 350);
  }

  function updateField(field: SchemaField, raw: unknown) {
    const coerced = coerceFieldValue(field.kind, raw);
    const values = { ...form.getValues(), [field.name]: coerced };
    form.setValue(field.name, coerced, { shouldDirty: true });
    onChange(values);
    scheduleValidate(values);
  }

  if (!definition) {
    return (
      <p className="text-sm text-muted-foreground">
        Node type not in catalog — use Advanced JSON.
      </p>
    );
  }

  if (fields.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No config fields for this node.
      </p>
    );
  }

  return (
    <form className="space-y-3" onSubmit={(event) => event.preventDefault()}>
      {fields.map((field) => (
        <WorkflowFieldRenderer
          key={field.name}
          field={field}
          value={form.watch(field.name)}
          error={serverErrors[field.name]}
          onChange={(value) => updateField(field, value)}
        />
      ))}
      {serverErrors._form ? (
        <p className="text-xs text-destructive" role="alert">
          {serverErrors._form}
        </p>
      ) : null}
    </form>
  );
}
