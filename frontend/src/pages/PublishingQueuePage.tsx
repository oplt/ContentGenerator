import { useMutation, useQuery } from "@tanstack/react-query";
import { cancelPublishingJob, getPublishedPosts, getPublishingJobs, retryPublishingJob } from "../api/publishing";
import { queryClient } from "../lib/queryClient";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function PublishingQueuePage() {
  const jobs = useQuery({ queryKey: ["publishing", "jobs"], queryFn: getPublishingJobs, refetchInterval: 10_000 });
  const posts = useQuery({ queryKey: ["publishing", "posts"], queryFn: getPublishedPosts });
  const retryMutation = useMutation({
    mutationFn: retryPublishingJob,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["publishing", "jobs"] });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: cancelPublishingJob,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["publishing", "jobs"] });
    },
  });

  if (jobs.isLoading || posts.isLoading) {
    return <LoadingState label="Loading publish queue" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Publish Queue</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Monitor scheduled jobs, operator recovery actions, and live post outputs.
        </p>
      </Card>

      <div className="grid gap-4">
        {(jobs.data ?? []).map((job) => (
          <Card key={job.id} className="p-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-lg font-semibold capitalize">{job.platform}</h2>
                <p className="text-sm text-muted-foreground">
                  {job.status} · retry #{job.retry_count}
                </p>
                {job.failure_reason && (
                  <p className="mt-2 text-sm text-destructive">{job.failure_reason}</p>
                )}
                {job.recovery_actions.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {job.recovery_actions.map((action) => (
                      <span key={action} className="rounded-full border px-2 py-1">
                        {action}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => retryMutation.mutate(job.id)}
                  disabled={retryMutation.isPending}
                >
                  Retry
                </Button>
                <Button
                  variant="outline"
                  onClick={() => cancelMutation.mutate(job.id)}
                  disabled={cancelMutation.isPending || !["scheduled", "pending", "failed"].includes(job.status)}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-semibold">Published Posts</h2>
        <div className="mt-4 space-y-3">
          {(posts.data ?? []).map((post) => (
            <div key={post.id} className="rounded-2xl border border-border p-4">
              <p className="font-medium capitalize">{post.platform}</p>
              <p className="text-sm text-muted-foreground">{post.external_url ?? "No external URL"}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
