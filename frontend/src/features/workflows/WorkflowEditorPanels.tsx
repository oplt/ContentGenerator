import { useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import type {
  DryRunOptions,
  NodeTestResult,
  WorkflowGraphNode,
  WorkflowNodeDefinition,
} from "../../api/workflows";
import { WorkflowNodeConfigForm } from "./WorkflowNodeConfigForm";
import { WorkflowPortHandle } from "./WorkflowPortHandle";

type Props = {
  selected: WorkflowGraphNode | null;
  definition: WorkflowNodeDefinition | null;
  onConfigChange: (config: Record<string, unknown>) => void;
  testInputs: string;
  onTestInputsChange: (value: string) => void;
  onTestNode: () => void;
  testBusy: boolean;
  testResult: NodeTestResult | null;
};

export function WorkflowStepConfigPanel({
  selected,
  definition,
  onConfigChange,
  testInputs,
  onTestInputsChange,
  onTestNode,
  testBusy,
  testResult,
}: Props) {
  const [advancedJson, setAdvancedJson] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("{}");
  const [jsonError, setJsonError] = useState<string | null>(null);

  useEffect(() => {
    // A new node selection owns a fresh editor mode and JSON draft.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAdvancedJson(false);
    setJsonError(null);
    if (selected) {
      setJsonDraft(JSON.stringify(selected.config ?? {}, null, 2));
    }
  }, [selected?.id, selected?.type]);

  if (!selected) {
    return <p className="text-sm text-muted-foreground">Select a step</p>;
  }

  return (
    <>
      <div>
        <label className="mb-1 block text-sm text-muted-foreground">Node id</label>
        <Input value={selected.id} disabled />
      </div>
      <div>
        <label className="mb-1 block text-sm text-muted-foreground">Type</label>
        <Input
          value={definition ? `${definition.display_name} (${selected.type})` : selected.type}
          disabled
        />
      </div>
      {definition?.description ? (
        <p className="text-xs text-muted-foreground">{definition.description}</p>
      ) : null}

      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Inputs</p>
        <WorkflowPortHandle direction="input" ports={definition?.input_ports ?? []} />
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Outputs</p>
        <WorkflowPortHandle direction="output" ports={definition?.output_ports ?? []} />
      </div>

      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">Configuration</p>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={advancedJson}
            onChange={(event) => {
              const next = event.target.checked;
              setAdvancedJson(next);
              if (next) {
                setJsonDraft(JSON.stringify(selected.config ?? {}, null, 2));
                setJsonError(null);
              }
            }}
          />
          Advanced JSON
        </label>
      </div>

      {advancedJson ? (
        <div>
          <Textarea
            className="min-h-28 font-mono text-xs"
            value={jsonDraft}
            onChange={(event) => {
              const text = event.target.value;
              setJsonDraft(text);
              try {
                onConfigChange(JSON.parse(text) as Record<string, unknown>);
                setJsonError(null);
              } catch {
                setJsonError("Invalid JSON");
              }
            }}
          />
          {jsonError ? <p className="mt-1 text-xs text-destructive">{jsonError}</p> : null}
        </div>
      ) : (
        <WorkflowNodeConfigForm
          nodeType={selected.type}
          version={selected.version}
          definition={definition}
          config={selected.config ?? {}}
          onChange={onConfigChange}
        />
      )}

      <div>
        <label className="mb-1 block text-sm text-muted-foreground">Test inputs JSON</label>
        <Textarea
          className="min-h-24 font-mono text-xs"
          value={testInputs}
          onChange={(event) => onTestInputsChange(event.target.value)}
        />
      </div>
      <Button size="sm" variant="secondary" disabled={testBusy} onClick={onTestNode}>
        {testBusy ? "Testing…" : "Test node"}
      </Button>
      {testResult ? (
        <div className="space-y-2 rounded border border-border p-2 text-xs">
          <p className="font-medium">
            {testResult.node_type} · {testResult.status}
          </p>
          <pre className="overflow-auto whitespace-pre-wrap">
            {JSON.stringify(
              {
                inputs: testResult.inputs,
                output: testResult.output,
                error: testResult.error,
              },
              null,
              2,
            )}
          </pre>
        </div>
      ) : null}
    </>
  );
}

type ActionsProps = {
  busy: boolean;
  hasGraph: boolean;
  dryRunOptions: DryRunOptions;
  onDryRunOptionsChange: (next: DryRunOptions) => void;
  onDraft: () => void;
  onValidate: () => void;
  onPublish: () => void;
  onTestRun: () => void;
};

export function WorkflowEditorActions({
  busy,
  hasGraph,
  dryRunOptions,
  onDryRunOptionsChange,
  onDraft,
  onValidate,
  onPublish,
  onTestRun,
}: ActionsProps) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={dryRunOptions.dry_run}
            onChange={(event) =>
              onDryRunOptionsChange({ ...dryRunOptions, dry_run: event.target.checked })
            }
          />
          Dry-run
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={dryRunOptions.mock_generation}
            onChange={(event) =>
              onDryRunOptionsChange({
                ...dryRunOptions,
                mock_generation: event.target.checked,
              })
            }
          />
          Mock generation
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={dryRunOptions.simulate_approval}
            onChange={(event) =>
              onDryRunOptionsChange({
                ...dryRunOptions,
                simulate_approval: event.target.checked,
              })
            }
          />
          Simulate approval
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy || !hasGraph} onClick={onDraft}>
          Save Draft
        </Button>
        <Button variant="secondary" disabled={busy || !hasGraph} onClick={onValidate}>
          Validate
        </Button>
        <Button disabled={busy || !hasGraph} onClick={onPublish}>
          Publish Version
        </Button>
        <Button variant="outline" disabled={busy} onClick={onTestRun}>
          Test Run
        </Button>
      </div>
    </div>
  );
}
