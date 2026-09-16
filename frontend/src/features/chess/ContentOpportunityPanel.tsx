import { useQuery } from "@tanstack/react-query";
import { getChessGameContentScore } from "../../api/chessData";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";

export type ContentOpportunityPanelProps = {
  gameId: string;
};

export function ContentOpportunityPanel({ gameId }: ContentOpportunityPanelProps) {
  const { tenantId, enabled } = useTenantScope();
  const query = useQuery({
    queryKey: queryKeys.chessContentScore(tenantId ?? "none", gameId),
    queryFn: () => getChessGameContentScore(gameId),
    enabled: Boolean(enabled && gameId),
  });

  const score = query.data;
  const components = Object.entries(score?.components ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium text-foreground">Content opportunity</p>
        {score ? (
          <p className="text-lg tabular-nums text-foreground">
            {score.score}
            <span className="ml-1 text-xs text-muted-foreground">/ 100</span>
          </p>
        ) : null}
      </div>
      {query.isLoading ? (
        <p className="text-muted-foreground">Loading score…</p>
      ) : null}
      {score ? (
        <>
          <p className="text-xs text-muted-foreground">
            {score.formula_version}
            {score.persisted === false ? " · metadata only (run analysis to enrich)" : " · persisted"}
          </p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {components.map(([name, value]) => (
              <li key={name} className="flex justify-between gap-2">
                <span>{name.replaceAll("_", " ")}</span>
                <span className="tabular-nums text-foreground">{value}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {query.isError ? (
        <p className="text-destructive">
          {query.error instanceof Error ? query.error.message : "Could not load score"}
        </p>
      ) : null}
    </div>
  );
}
