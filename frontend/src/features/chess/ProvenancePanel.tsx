import { useQuery } from "@tanstack/react-query";
import { getChessGameProvenance, type ChessGameProvenance } from "../../api/chessData";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";
import { formatDisplayDateTime } from "./sourceFreshness";

export type ProvenancePanelProps = {
  gameId: string;
  /** When false (famous), avoid fresh/stale wording around retrieval (§24). */
  showFreshnessLanguage?: boolean;
};

function SourceRow({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (!value) return null;
  return (
    <li className="flex justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="max-w-[60%] truncate text-right text-foreground" title={value}>
        {value}
      </span>
    </li>
  );
}

function SourceBlock({
  source,
  retrievedLabel,
}: {
  source: NonNullable<ChessGameProvenance["primary_source"]>;
  retrievedLabel: string;
}) {
  return (
    <ul className="space-y-1 text-xs">
      <SourceRow label="Source" value={source.provider} />
      <SourceRow label="URL" value={source.source_url} />
      <SourceRow label="License" value={source.license_note} />
      <SourceRow
        label={retrievedLabel}
        value={formatDisplayDateTime(source.retrieved_at)}
      />
    </ul>
  );
}

export function ProvenancePanel({
  gameId,
  showFreshnessLanguage = true,
}: ProvenancePanelProps) {
  const { tenantId, enabled } = useTenantScope();
  const query = useQuery({
    queryKey: queryKeys.chessGameProvenance(tenantId ?? "none", gameId),
    queryFn: () => getChessGameProvenance(gameId),
    enabled: Boolean(enabled && gameId),
  });

  const data = query.data;
  const retrievedLabel = showFreshnessLanguage ? "Source retrieved" : "Source recorded";

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3 text-sm">
      <p className="font-medium text-foreground">Source provenance</p>
      {query.isLoading ? <p className="text-muted-foreground">Loading provenance…</p> : null}
      {data ? (
        <>
          <p className="text-xs text-muted-foreground">{data.evidence_note}</p>
          {data.primary_source ? (
            <SourceBlock source={data.primary_source} retrievedLabel={retrievedLabel} />
          ) : null}
          {data.sources.length > 1 ? (
            <p className="text-xs text-muted-foreground">
              {data.sources.length} sources linked to this game
            </p>
          ) : null}
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer">Original PGN</summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-background p-2 text-[11px] text-foreground">
              {data.normalized_pgn}
            </pre>
          </details>
        </>
      ) : null}
      {query.isError ? (
        <p className="text-destructive">
          {query.error instanceof Error ? query.error.message : "Could not load provenance"}
        </p>
      ) : null}
    </div>
  );
}
