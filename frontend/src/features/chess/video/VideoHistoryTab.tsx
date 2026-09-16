import { Download, Trash2 } from "lucide-react";
import type { ChessVideoJob } from "../../../api/chessVideos";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { formatDate, formatDuration, gameTitle, JobStatusBadge } from "./status";

export function VideoHistoryTab({
  jobs,
  loading,
  error,
  deleteError,
  deletingJobId,
  onRetryLoad,
  onPreview,
  onDelete,
  onCreate,
}: {
  jobs: ChessVideoJob[];
  loading: boolean;
  error: boolean;
  deleteError: unknown;
  deletingJobId?: string;
  onRetryLoad: () => void;
  onPreview: (jobId: string) => void;
  onDelete: (jobId: string) => void;
  onCreate: () => void;
}) {
  return (
    <Card className="p-4 sm:p-6">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-medium text-foreground">Recent videos</h2>
          <p className="text-sm text-muted-foreground">Review previous renders and reopen completed videos.</p>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={onCreate}>
          Create new
        </Button>
      </div>

      {loading ? <LoadingState label="Loading chess videos" /> : null}
      {error ? (
        <ErrorState message="Could not load chess video jobs." onRetry={onRetryLoad} />
      ) : null}

      {!loading && !error && jobs.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center">
          <p className="font-medium text-foreground">No generated videos yet.</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first chess video to see it here.
          </p>
        </div>
      ) : null}

      {jobs.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-border text-xs font-medium text-muted-foreground">
              <tr>
                <th className="py-2 pr-4">Game</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Moves</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 pr-4">Duration</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td className="max-w-[260px] py-3 pr-4">
                    <button
                      type="button"
                      className="block truncate text-left font-medium text-foreground hover:underline"
                      onClick={() => onPreview(job.id)}
                    >
                      {gameTitle(job)}
                    </button>
                    <p className="truncate text-xs text-muted-foreground">{job.event || job.id}</p>
                  </td>
                  <td className="py-3 pr-4">
                    <JobStatusBadge status={job.status} />
                  </td>
                  <td className="py-3 pr-4 text-muted-foreground">{job.move_count}</td>
                  <td className="py-3 pr-4 text-muted-foreground">{formatDate(job.created_at)}</td>
                  <td className="py-3 pr-4 text-muted-foreground">{formatDuration(job.duration_seconds)}</td>
                  <td className="py-3">
                    <div className="flex justify-end gap-1">
                      <Button type="button" variant="ghost" size="sm" onClick={() => onPreview(job.id)}>
                        {job.video_public_url ? "Preview" : "View"}
                      </Button>
                      {job.video_public_url ? (
                        <Button asChild variant="ghost" size="sm">
                          <a href={job.video_public_url} download>
                            <Download className="size-4" />
                          </a>
                        </Button>
                      ) : null}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-muted-foreground hover:text-destructive"
                        aria-label={`Delete chess video job ${job.id.slice(0, 8)}`}
                        disabled={deletingJobId === job.id}
                        onClick={() => onDelete(job.id)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {deleteError ? (
        <div className="mt-4">
          <ErrorState
            message={
              deleteError instanceof Error
                ? deleteError.message
                : "Could not delete chess video job."
            }
          />
        </div>
      ) : null}
    </Card>
  );
}
