import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  enqueueChessGameAnalysis,
  getChessAnalysisJob,
  getChessGameAnalysis,
  type ChessAnalysisJob,
  type ChessPositionAnalysis,
} from "../../api/chessData";
import { Button } from "../../components/ui/button";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function formatEval(row: ChessPositionAnalysis | undefined): string {
  if (!row) return "—";
  if (row.mate_in != null) {
    const sign = row.mate_in > 0 ? "+" : "";
    return `M${sign}${row.mate_in}`;
  }
  if (row.evaluation_cp == null) return "—";
  return `${(row.evaluation_cp / 100).toFixed(2)}`;
}

export type AnalyzeGameActionProps = {
  gameId: string;
  activePly?: number | null;
};

export function AnalyzeGameAction({ gameId, activePly = null }: AnalyzeGameActionProps) {
  const { tenantId, enabled } = useTenantScope();
  const queryClient = useQueryClient();

  const latestQuery = useQuery({
    queryKey: queryKeys.chessGameAnalysis(tenantId ?? "none", gameId),
    queryFn: () => getChessGameAnalysis(gameId),
    enabled: Boolean(enabled && gameId),
    retry: false,
  });

  const jobId = latestQuery.data?.id;
  const jobQuery = useQuery({
    queryKey: queryKeys.chessAnalysisJob(tenantId ?? "none", jobId ?? "none"),
    queryFn: () => getChessAnalysisJob(jobId!),
    enabled: Boolean(enabled && jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL.has(status)) return false;
      return 1500;
    },
  });

  const analysis: ChessAnalysisJob | undefined = jobQuery.data ?? latestQuery.data;

  const enqueueMutation = useMutation({
    mutationFn: () => enqueueChessGameAnalysis(gameId, {}),
    onSuccess: async (job) => {
      if (tenantId) {
        queryClient.setQueryData(queryKeys.chessAnalysisJob(tenantId, job.id), job);
        queryClient.setQueryData(queryKeys.chessGameAnalysis(tenantId, gameId), job);
        await queryClient.invalidateQueries({
          queryKey: queryKeys.chessGameAnalysis(tenantId, gameId),
        });
        await queryClient.invalidateQueries({
          queryKey: queryKeys.chessContentScore(tenantId, gameId),
        });
      }
    },
  });

  const plyRow = analysis?.positions.find((row) => row.ply === activePly);
  const moments = analysis?.critical_moments ?? [];
  const patterns = analysis?.tactical_patterns ?? [];
  const plyMoments = activePly
    ? moments.filter((moment) => moment.ply === activePly)
    : moments.slice(0, 8);
  const plyPatterns = activePly
    ? patterns.filter((pattern) => pattern.ply === activePly)
    : patterns.slice(0, 8);
  const busy =
    enqueueMutation.isPending ||
    analysis?.status === "queued" ||
    analysis?.status === "running";

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium text-foreground">Engine analysis</p>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() => enqueueMutation.mutate()}
        >
          {busy ? "Analyzing…" : analysis ? "Re-analyze" : "Analyze with Stockfish"}
        </Button>
      </div>
      {analysis ? (
        <p className="text-muted-foreground">
          Status: {analysis.status}
          {analysis.engine_name ? ` · ${analysis.engine_name}` : ""}
          {activePly ? ` · ply ${activePly} eval ${formatEval(plyRow)}` : ""}
          {plyRow?.best_move_san ? ` · best ${plyRow.best_move_san}` : ""}
          {moments.length ? ` · ${moments.length} critical moments` : ""}
          {patterns.length ? ` · ${patterns.length} tactics` : ""}
        </p>
      ) : (
        <p className="text-muted-foreground">
          Queue Stockfish in the background. Scores use White&apos;s perspective.
        </p>
      )}
      {plyMoments.length > 0 ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {plyMoments.map((moment) => (
            <li key={moment.id}>
              <span className="font-medium text-foreground">{moment.classification}</span>
              {" · "}
              ply {moment.ply}
              {" · "}
              {moment.heuristic_summary}
            </li>
          ))}
        </ul>
      ) : null}
      {plyPatterns.length > 0 ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {plyPatterns.map((pattern) => (
            <li key={pattern.id}>
              <span className="font-medium text-foreground">{pattern.pattern}</span>
              {" · "}
              {(pattern.confidence * 100).toFixed(0)}%
              {" · "}
              {pattern.summary}
            </li>
          ))}
        </ul>
      ) : null}
      {analysis?.error_message ? (
        <p className="text-destructive">{analysis.error_message}</p>
      ) : null}
      {enqueueMutation.isError ? (
        <p className="text-destructive">
          {enqueueMutation.error instanceof Error
            ? enqueueMutation.error.message
            : "Could not queue analysis"}
        </p>
      ) : null}
    </div>
  );
}
