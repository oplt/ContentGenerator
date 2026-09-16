import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import type { DryRunOptions, NodeTestResult, WorkflowGraphNode } from "../../api/workflows";

type Props = {
  selected: WorkflowGraphNode | null;
  onConfigChange: (config: Record<string, unknown>) => void;
  testInputs: string;
  onTestInputsChange: (value: string) => void;
  onTestNode: () => void;
  testBusy: boolean;
  testResult: NodeTestResult | null;
};

export function WorkflowStepConfigPanel({
  selected,
  onConfigChange,
  testInputs,
  onTestInputsChange,
  onTestNode,
  testBusy,
  testResult,
}: Props) {
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
        <Input value={selected.type} disabled />
      </div>
      <div>
        <label className="mb-1 block text-sm text-muted-foreground">Config JSON</label>
        <Textarea
          className="min-h-28 font-mono text-xs"
          value={JSON.stringify(selected.config ?? {}, null, 2)}
          onChange={(event) => {
            try {
              onConfigChange(JSON.parse(event.target.value) as Record<string, unknown>);
            } catch {
              /* keep typing */
            }
          }}
        />
      </div>
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
