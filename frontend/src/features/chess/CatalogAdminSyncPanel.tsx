/**
 * §25 — privileged catalog sync controls (jobs), separate from browsing.
 *
 * Browse/search never starts sync. These buttons enqueue ChessCatalogJob only.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  enqueueChessCatalogJob,
  getChessCatalogJob,
  type ChessCatalogJob,
} from "../../api/chessData";
import { useAuth } from "../auth/AuthContext";
import { canWriteContent } from "../auth/access";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { useTenantScope } from "../../hooks/useTenantScope";
import { queryKeys } from "../../lib/queryKeys";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function JobStatusLine({ job }: { job: ChessCatalogJob | null }) {
  if (!job) return null;
  return (
    <p className="text-xs text-muted-foreground" data-testid="catalog-admin-job-status">
      Last job · {job.kind} · {job.status}
      {job.error_message ? ` · ${job.error_message}` : ""}
    </p>
  );
}

export function CatalogAdminSyncPanel() {
  const { currentUser } = useAuth();
  const { tenantId, enabled } = useTenantScope();
  const canWrite = canWriteContent(currentUser, tenantId);
  const [archivePath, setArchivePath] = useState("");
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: queryKeys.chessCatalogJob(tenantId ?? "none", lastJobId ?? "none"),
    queryFn: () => getChessCatalogJob(lastJobId!),
    enabled: Boolean(enabled && lastJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || TERMINAL.has(status)) return false;
      return 2000;
    },
  });

  const enqueue = useMutation({
    mutationFn: (payload: Parameters<typeof enqueueChessCatalogJob>[0]) =>
      enqueueChessCatalogJob(payload),
    onSuccess: (job) => setLastJobId(job.id),
  });

  if (!canWrite) return null;

  const busy = enqueue.isPending;

  return (
    <Card className="space-y-3 border-dashed p-4" data-testid="catalog-admin-sync">
      <div>
        <p className="text-sm font-medium text-foreground">Catalog sync (admin)</p>
        <p className="text-xs text-muted-foreground">
          Queues background jobs. Browsing and search never start provider sync.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() =>
            enqueue.mutate({
              kind: "provider_sync",
              params: { provider: "lichess_masters", max_games: 15 },
            })
          }
        >
          Run recent-game sync
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() => enqueue.mutate({ kind: "daily_puzzle_sync", params: {} })}
        >
          Refresh daily puzzle
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={busy}
          onClick={() => enqueue.mutate({ kind: "enrich_famous", params: {} })}
        >
          Enrich famous catalog
        </Button>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-1">
          <label className="text-xs text-muted-foreground" htmlFor="chess-archive-path">
            Import archive (server file path)
          </label>
          <Input
            id="chess-archive-path"
            value={archivePath}
            onChange={(e) => setArchivePath(e.target.value)}
            placeholder="/data/archive.pgn"
            disabled={busy}
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || !archivePath.trim()}
          onClick={() =>
            enqueue.mutate({
              kind: "pgn_import",
              params: { file_path: archivePath.trim() },
            })
          }
        >
          Import archive
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Reanalyze uses Analyze on a selected game (Stockfish profile + fingerprint reuse).
      </p>
      <JobStatusLine job={jobQuery.data ?? enqueue.data ?? null} />
      {enqueue.isError ? (
        <p className="text-xs text-destructive">
          {enqueue.error instanceof Error ? enqueue.error.message : "Could not queue job"}
        </p>
      ) : null}
    </Card>
  );
}
