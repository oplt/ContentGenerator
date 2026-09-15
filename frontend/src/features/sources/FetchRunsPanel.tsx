import { useQuery } from "@tanstack/react-query";
import { getSourceFetchRuns } from "../../api/sources";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";
import { queryPolicy } from "../../lib/queryPolicy";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";

export function FetchRunsPanel({
  active,
  sourceNameById,
}: {
  active: boolean;
  sourceNameById: Map<string, string>;
}) {
  const { tenantId, enabled } = useTenantScope();
  const fetchRuns = useQuery({
    queryKey: queryKeys.sourceFetchRuns(tenantId ?? "none"),
    queryFn: getSourceFetchRuns,
    enabled: enabled && active,
    ...queryPolicy.fast,
  });

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Fetch runs</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Recent ingestion activity. Long jobs surface here after the HTTP trigger returns.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            void fetchRuns.refetch();
          }}
          disabled={fetchRuns.isFetching}
        >
          {fetchRuns.isFetching ? "Refreshing…" : "Refresh"}
        </Button>
      </div>
      <div className="mt-4 space-y-3">
        {fetchRuns.isLoading ? (
          <LoadingState label="Loading fetch runs" />
        ) : fetchRuns.isError ? (
          <ErrorState
            message="Fetch runs could not be loaded."
            onRetry={() => {
              void fetchRuns.refetch();
            }}
          />
        ) : (fetchRuns.data?.length ?? 0) === 0 ? (
          <EmptyState title="No fetch runs yet" description="Run Ingest Now to create activity." />
        ) : (
          fetchRuns.data?.map((run) => (
            <div key={run.id} className="inset-panel flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-medium">
                  {sourceNameById.get(run.source_id) ?? run.source_id.slice(0, 8)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {run.status}
                  {run.duration_ms != null ? ` · ${run.duration_ms}ms` : ""}
                  {` · found ${run.articles_found} / new ${run.new_articles}`}
                </p>
                {run.error_message ? (
                  <p className="mt-1 text-sm text-destructive">{run.error_message}</p>
                ) : null}
              </div>
              <Badge variant={run.status === "success" ? "success" : "warning"}>{run.status}</Badge>
            </div>
          ))
        )}
      </div>
    </Card>
  );
}
