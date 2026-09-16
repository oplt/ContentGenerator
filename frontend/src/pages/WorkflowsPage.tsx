import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  createWorkflowDefinition,
  listWorkflowDefinitions,
  saveWorkflowDraft,
  DEFAULT_LINEAR_GRAPH,
} from "../api/workflows";
import { useTenantScope } from "../hooks/useTenantScope";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function statusVariant(status: string): "muted" | "success" | "warning" {
  if (status === "active") return "success";
  if (status === "archived") return "muted";
  return "warning";
}

export default function WorkflowsPage() {
  const { tenantId, enabled } = useTenantScope();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const definitions = useQuery({
    queryKey: queryKeys.workflowDefinitions(tenantId ?? "none"),
    queryFn: ({ signal }) => listWorkflowDefinitions({ signal }),
    enabled,
    ...queryPolicy.moderate,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim();
      if (!trimmed) throw new Error("Name is required");
      const slug = slugify(trimmed) || `workflow-${Date.now()}`;
      const created = await createWorkflowDefinition({ name: trimmed, slug });
      await saveWorkflowDraft(created.id, { graph: DEFAULT_LINEAR_GRAPH });
      return created;
    },
    onSuccess: async (created) => {
      setName("");
      setError(null);
      if (tenantId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.workflowDefinitions(tenantId),
        });
      }
      navigate(`/dashboard/workflows/${created.id}`);
    },
    onError: (err: Error) => setError(err.message || "Failed to create workflow"),
  });

  if (definitions.isLoading) return <LoadingState label="Loading workflows" />;
  if (definitions.isError) {
    return <ErrorState title="Could not load workflows" message="Retry shortly." />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Workflows</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Reusable content automation templates. Edit steps, validate, then publish a version.
        </p>
      </Card>

      <Card className="p-5">
        <h2 className="text-lg font-semibold">Create workflow</h2>
        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Daily chess caption"
            aria-label="Workflow name"
          />
          <Button
            variant="primary"
            disabled={createMutation.isPending || !name.trim()}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
        {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
      </Card>

      <div className="grid gap-3">
        {(definitions.data ?? []).length === 0 && (
          <Card className="p-5 text-sm text-muted-foreground">No workflows yet.</Card>
        )}
        {(definitions.data ?? []).map((row) => (
          <Card key={row.id} className="p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold">{row.name}</h2>
                  <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {row.slug}
                  {row.current_version_id
                    ? ` · published ${row.current_version_id.slice(0, 8)}`
                    : " · draft only"}
                </p>
              </div>
              <Button asChild variant="outline">
                <Link to={`/dashboard/workflows/${row.id}`}>Open editor</Link>
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
