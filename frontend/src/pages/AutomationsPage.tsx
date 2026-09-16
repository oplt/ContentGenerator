import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  createAutomation,
  listAutomations,
  listWorkflowBrands,
  listWorkflowDefinitions,
  updateAutomation,
} from "../api/workflows";
import { getSocialAccounts } from "../api/publishing";
import { useTenantScope } from "../hooks/useTenantScope";
import { useAccountSelection } from "../hooks/useAccountSelection";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { SocialAccountSelector } from "../components/dashboard/SocialAccountSelector";

export default function AutomationsPage() {
  const { tenantId, enabled } = useTenantScope();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const [name, setName] = useState("");
  const [definitionId, setDefinitionId] = useState("");
  const [brandId, setBrandId] = useState("");
  const [triggerType, setTriggerType] = useState("manual");
  const [cron, setCron] = useState("0 9 * * *");
  const [timezone, setTimezone] = useState("Europe/Brussels");
  const [message, setMessage] = useState<string | null>(null);

  const automations = useQuery({
    queryKey: queryKeys.workflowAutomations(tenantId ?? "none"),
    queryFn: ({ signal }) => listAutomations({ signal }),
    enabled,
    ...queryPolicy.moderate,
  });
  const definitions = useQuery({
    queryKey: queryKeys.workflowDefinitions(tenantId ?? "none"),
    queryFn: ({ signal }) => listWorkflowDefinitions({ signal }),
    enabled,
    ...queryPolicy.moderate,
  });
  const brands = useQuery({
    queryKey: queryKeys.workflowBrands(tenantId ?? "none"),
    queryFn: ({ signal }) => listWorkflowBrands({ signal }),
    enabled,
    ...queryPolicy.moderate,
  });
  const accounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled,
    ...queryPolicy.moderate,
  });

  const publishedDefs = useMemo(
    () => (definitions.data ?? []).filter((row) => row.current_version_id),
    [definitions.data]
  );

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!name.trim() || !definitionId) throw new Error("Name and workflow required");
      return createAutomation({
        name: name.trim(),
        workflow_definition_id: definitionId,
        brand_id: brandId || undefined,
        enabled: false,
        trigger_type: triggerType,
          trigger_config:
          triggerType === "schedule" ? { kind: "cron", expr: cron } : {},
        timezone,
        social_account_ids: selectedIds,
      });
    },
    onSuccess: async () => {
      setName("");
      setMessage("Automation created (disabled until you enable it)");
      if (tenantId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.workflowAutomations(tenantId),
        });
      }
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled: next }: { id: string; enabled: boolean }) =>
      updateAutomation(id, { enabled: next }),
    onSuccess: async () => {
      if (tenantId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.workflowAutomations(tenantId),
        });
      }
    },
  });

  if (automations.isLoading || definitions.isLoading) {
    return <LoadingState label="Loading automations" />;
  }
  if (automations.isError) {
    return <ErrorState title="Could not load automations" message="Retry shortly." />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Automations</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bind a published workflow to a brand, schedule, and target accounts.
        </p>
      </Card>

      <Card className="p-5 space-y-4">
        <h2 className="text-lg font-semibold">Create automation</h2>
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Chess daily historical"
          aria-label="Automation name"
        />
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Workflow</span>
          <select
            className="h-10 w-full rounded border border-border bg-background px-3 text-sm"
            value={definitionId}
            onChange={(event) => setDefinitionId(event.target.value)}
          >
            <option value="">Select published workflow</option>
            {publishedDefs.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Brand</span>
          <select
            className="h-10 w-full rounded border border-border bg-background px-3 text-sm"
            value={brandId}
            onChange={(event) => setBrandId(event.target.value)}
          >
            <option value="">Default brand</option>
            {(brands.data ?? []).map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">Trigger</span>
          <select
            className="h-10 w-full rounded border border-border bg-background px-3 text-sm"
            value={triggerType}
            onChange={(event) => setTriggerType(event.target.value)}
          >
            <option value="manual">manual</option>
            <option value="schedule">schedule</option>
          </select>
        </label>
        {triggerType === "schedule" && (
          <div className="grid gap-3 md:grid-cols-2">
            <Input value={cron} onChange={(event) => setCron(event.target.value)} aria-label="Cron" />
            <Input
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              aria-label="Timezone"
            />
          </div>
        )}
        <SocialAccountSelector
          accounts={accounts.data ?? []}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          label="Targets"
        />
        <Button
          variant="primary"
          disabled={createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          Create
        </Button>
        {message && <p className="text-sm text-muted-foreground">{message}</p>}
      </Card>

      <div className="grid gap-3">
        {(automations.data ?? []).map((row) => (
          <Card key={row.id} className="p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold">{row.name}</h2>
                  <Badge variant={row.enabled ? "success" : "muted"}>
                    {row.enabled ? "enabled" : "disabled"}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {row.trigger_type}
                  {row.next_run_at
                    ? ` · next ${new Date(row.next_run_at).toLocaleString()}`
                    : ""}
                  {` · ${row.targets.length} targets`}
                </p>
              </div>
              <Button
                variant="outline"
                disabled={toggleMutation.isPending}
                onClick={() =>
                  toggleMutation.mutate({ id: row.id, enabled: !row.enabled })
                }
              >
                {row.enabled ? "Disable" : "Enable"}
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
