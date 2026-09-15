import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import type { RawArticlePage, Source, SourceHealth } from "../../api/sources";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SourceEditRow } from "./components";

type UpdateSourceMutation = UseMutationResult<
  Source,
  Error,
  { id: string; payload: Record<string, unknown> }
>;
type SourceIdMutation = UseMutationResult<unknown, Error, string>;

export type ConfiguredSourcesPanelProps = {
  sources: Source[];
  health: UseQueryResult<SourceHealth[], Error>;
  rawArticles: UseQueryResult<RawArticlePage, Error>;
  healthBySourceId: Map<string, SourceHealth>;
  editingSourceId: string | null;
  setEditingSourceId: (id: string | null) => void;
  savingSourceId: string | null;
  setSavingSourceId: (id: string | null) => void;
  deletingSourceId: string | null;
  setDeletingSourceId: (id: string | null) => void;
  lastIngestRunId: string | null;
  updateMutation: UpdateSourceMutation;
  ingestMutation: SourceIdMutation;
  manualPollMutation: SourceIdMutation;
  disableMutation: SourceIdMutation;
  deleteMutation: SourceIdMutation;
  onOpenActivity: () => void;
  onAddSource: () => void;
};

export function ConfiguredSourcesPanel({
  sources,
  health,
  rawArticles,
  healthBySourceId,
  editingSourceId,
  setEditingSourceId,
  savingSourceId,
  setSavingSourceId,
  deletingSourceId,
  setDeletingSourceId,
  lastIngestRunId,
  updateMutation,
  ingestMutation,
  manualPollMutation,
  disableMutation,
  deleteMutation,
  onOpenActivity,
  onAddSource,
}: ConfiguredSourcesPanelProps) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Health uses cached connector status. Refresh only when you need a live check.
        </p>
        <Button
          variant="outline"
          onClick={() => {
            void health.refetch();
          }}
          disabled={health.isFetching}
        >
          {health.isFetching ? "Refreshing…" : "Refresh health"}
        </Button>
      </div>

      {sources.length > 0 ? (
        <>
          <div className="grid gap-4">
            {sources.map((source) => {
              const sourceHealth = healthBySourceId.get(source.id);
              return editingSourceId === source.id ? (
                <SourceEditRow
                  key={source.id}
                  source={source}
                  isSaving={savingSourceId === source.id && updateMutation.isPending}
                  onCancel={() => setEditingSourceId(null)}
                  onSave={async (values) => {
                    setSavingSourceId(source.id);
                    try {
                      await updateMutation.mutateAsync({ id: source.id, payload: values });
                      setEditingSourceId(null);
                    } finally {
                      setSavingSourceId(null);
                    }
                  }}
                />
              ) : (
                <Card
                  key={source.id}
                  className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between"
                >
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-semibold">{source.name}</h2>
                      <Badge variant={sourceHealth?.status === "healthy" ? "success" : "warning"}>
                        {sourceHealth?.status ?? (health.isLoading ? "…" : "unknown")}
                      </Badge>
                      <Badge variant="muted" className="capitalize">
                        {source.category}
                      </Badge>
                      <Badge
                        variant={source.source_tier === "authoritative" ? "default" : "muted"}
                        className="capitalize"
                      >
                        {source.source_tier ?? "signal"}
                      </Badge>
                      <Badge variant="muted" className="capitalize">
                        {source.content_vertical ?? "general"}
                      </Badge>
                      {source.legal_risk && <Badge variant="warning">Legal Risk</Badge>}
                      {source.tier1_confirmation_required && (
                        <Badge variant="warning">Tier1 Required</Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{source.url}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {source.source_type} · every {source.polling_interval_minutes} min · freshness{" "}
                      {source.freshness_decay_hours}h · {source.success_count} ok / {source.failure_count} fail
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      variant="outline"
                      onClick={() => ingestMutation.mutate(source.id)}
                      disabled={ingestMutation.isPending}
                    >
                      Ingest Now
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => manualPollMutation.mutate(source.id)}
                      disabled={manualPollMutation.isPending}
                    >
                      Manual Poll
                    </Button>
                    <Button variant="outline" onClick={() => setEditingSourceId(source.id)}>
                      Edit
                    </Button>
                    {source.active && (
                      <Button variant="outline" onClick={() => disableMutation.mutate(source.id)}>
                        Disable
                      </Button>
                    )}
                    <Button
                      variant="destructive"
                      onClick={async () => {
                        if (!window.confirm(`Delete source "${source.name}"?`)) return;
                        setDeletingSourceId(source.id);
                        try {
                          await deleteMutation.mutateAsync(source.id);
                        } finally {
                          setDeletingSourceId(null);
                        }
                      }}
                      disabled={deleteMutation.isPending && deletingSourceId === source.id}
                    >
                      {deleteMutation.isPending && deletingSourceId === source.id
                        ? "Deleting…"
                        : "Delete"}
                    </Button>
                  </div>
                </Card>
              );
            })}
          </div>

          {lastIngestRunId ? (
            <p className="text-sm text-muted-foreground">
              Last ingest run{" "}
              <button
                type="button"
                className="font-medium text-foreground underline"
                onClick={onOpenActivity}
              >
                {lastIngestRunId.slice(0, 8)}
              </button>{" "}
              — open Activity for status history.
            </p>
          ) : null}

          <Card className="p-5">
            <h2 className="text-lg font-semibold">Latest Raw Articles</h2>
            <div className="mt-4 space-y-3">
              {rawArticles.isError ? (
                <ErrorState
                  message="Raw articles could not be loaded."
                  onRetry={() => {
                    void rawArticles.refetch();
                  }}
                />
              ) : (rawArticles.data?.items.length ?? 0) === 0 ? (
                <EmptyState
                  title="No articles yet"
                  description="Ingest a source to populate the raw article feed."
                />
              ) : (
                rawArticles.data?.items.map((article) => (
                  <div key={article.id} className="inset-panel">
                    <a
                      href={article.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium hover:underline hover:text-primary"
                    >
                      {article.title}
                    </a>
                    <p className="mt-1 text-sm text-muted-foreground">{article.summary}</p>
                  </div>
                ))
              )}
            </div>
          </Card>
        </>
      ) : (
        <EmptyState
          title="No sources configured"
          description="Add from the library or create a manual source."
          action={
            <Button variant="outline" onClick={onAddSource}>
              Add source
            </Button>
          }
        />
      )}
    </>
  );
}
