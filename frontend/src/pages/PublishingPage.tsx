import { useMutation, useQuery } from "@tanstack/react-query";
import { getContentJobs } from "../api/content";
import { getPublishedPosts, getPublishingJobs, publishNow } from "../api/publishing";
import { queryClient } from "../lib/queryClient";
import { PublishingStatusCard } from "../components/dashboard/PublishingStatusCard";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function PublishingPage() {
  const jobs = useQuery({ queryKey: ["publishing", "jobs"], queryFn: getPublishingJobs, refetchInterval: 10_000 });
  const posts = useQuery({ queryKey: ["publishing", "posts"], queryFn: getPublishedPosts });
  const contentJobs = useQuery({ queryKey: ["content", "jobs"], queryFn: getContentJobs });
  const publishMutation = useMutation({
    mutationFn: publishNow,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["publishing", "jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["publishing", "posts"] }),
      ]);
    },
  });

  if (jobs.isLoading || posts.isLoading || contentJobs.isLoading) {
    return <LoadingState label="Loading publishing queue" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Publishing Queue</h1>
        <div className="mt-5 flex flex-wrap gap-3">
          {contentJobs.data?.slice(0, 6).map((job) => (
            <Button key={job.id} variant="outline" onClick={() => publishMutation.mutate({ content_job_id: job.id, dry_run: true })}>
              Publish job {job.id.slice(0, 8)}
            </Button>
          ))}
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {jobs.data?.map((job) => (
          <PublishingStatusCard key={job.id} job={job} />
        ))}
      </div>
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Published Posts</h2>
        <div className="mt-4 space-y-3">
          {posts.data?.map((post) => (
            <div key={post.id} className="rounded-2xl border border-border bg-muted/40 p-4">
              <p className="font-medium">{post.platform}</p>
              <p className="text-sm text-muted-foreground">{post.external_url ?? "No external URL"}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
