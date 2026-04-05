import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { sendApprovalRequest, getApprovalRequests } from "../api/approvals";
import { createContentPlan, generateContent, getContentJobs, getContentPlans } from "../api/content";
import { getPublishedPosts, getPublishingJobs, publishNow } from "../api/publishing";
import { getStoryClusters } from "../api/stories";
import { queryClient } from "../lib/queryClient";
import { ApprovalTimeline } from "../components/dashboard/ApprovalTimeline";
import { ContentPlanPanel } from "../components/dashboard/ContentPlanPanel";
import { PublishingStatusCard } from "../components/dashboard/PublishingStatusCard";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";

const TAB_PARAM = "tab";
const TABS = ["plans", "approvals", "publishing"] as const;
type Tab = (typeof TABS)[number];

function isValidTab(value: string | null): value is Tab {
  return TABS.includes(value as Tab);
}

// ─── Plans + Jobs tab ────────────────────────────────────────────────────────

function PlansTab() {
  const plans = useQuery({ queryKey: ["content", "plans"], queryFn: getContentPlans });
  const jobs = useQuery({ queryKey: ["content", "jobs"], queryFn: getContentJobs, refetchInterval: 10_000 });
  const stories = useQuery({ queryKey: ["stories"], queryFn: getStoryClusters });

  const createPlanMutation = useMutation({
    mutationFn: createContentPlan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["content", "plans"] });
    },
  });
  const generateMutation = useMutation({
    mutationFn: generateContent,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["content", "jobs"] });
    },
  });

  if (plans.isLoading || jobs.isLoading || stories.isLoading) {
    return <LoadingState label="Loading content queue" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h2 className="text-base font-semibold">Create plan from story</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {stories.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No stories available yet.</p>
          )}
          {stories.data?.slice(0, 5).map((story) => (
            <Button
              key={story.id}
              variant="outline"
              onClick={() => createPlanMutation.mutate({ story_cluster_id: story.id })}
              disabled={createPlanMutation.isPending}
            >
              Plan from {story.primary_topic}
            </Button>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Plans</h2>
          {plans.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content plans yet.</p>
          )}
          {plans.data?.map((plan) => (
            <ContentPlanPanel
              key={plan.id}
              plan={plan}
              onGenerate={() => generateMutation.mutate(plan.id)}
            />
          ))}
        </div>

        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Jobs</h2>
          {jobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No generation jobs yet.</p>
          )}
          {jobs.data?.map((job) => (
            <Card key={job.id} className="p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{job.job_type}</p>
                  <p className="text-xs text-muted-foreground">{job.stage}</p>
                </div>
                <Link to={`/dashboard/content/${job.id}`}>
                  <Button variant="outline" size="sm">Open</Button>
                </Link>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Approvals tab ───────────────────────────────────────────────────────────

function ApprovalsTab() {
  const approvals = useQuery({
    queryKey: ["approvals"],
    queryFn: getApprovalRequests,
    refetchInterval: 10_000,
  });
  const jobs = useQuery({ queryKey: ["content", "jobs"], queryFn: getContentJobs });

  const sendMutation = useMutation({
    mutationFn: sendApprovalRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });

  if (approvals.isLoading || jobs.isLoading) {
    return <LoadingState label="Loading approvals" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h2 className="text-base font-semibold">Send job for approval</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {jobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content jobs available.</p>
          )}
          {jobs.data?.slice(0, 6).map((job) => (
            <Button
              key={job.id}
              variant="outline"
              onClick={() => sendMutation.mutate({ content_job_id: job.id })}
              disabled={sendMutation.isPending}
            >
              Send {job.job_type} for approval
            </Button>
          ))}
        </div>
      </Card>

      {approvals.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">No approval requests yet.</p>
      )}
      {approvals.data?.map((approval) => (
        <Card key={approval.id} className="p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold capitalize">{approval.status}</h3>
              <p className="text-sm text-muted-foreground">{approval.recipient}</p>
            </div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {approval.provider}
            </p>
          </div>
          <div className="mt-4">
            <ApprovalTimeline approval={approval} />
          </div>
        </Card>
      ))}
    </div>
  );
}

// ─── Publishing tab ───────────────────────────────────────────────────────────

function PublishingTab() {
  const jobs = useQuery({
    queryKey: ["publishing", "jobs"],
    queryFn: getPublishingJobs,
    refetchInterval: 10_000,
  });
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
        <h2 className="text-base font-semibold">Publish job now</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {contentJobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content jobs available.</p>
          )}
          {contentJobs.data?.slice(0, 6).map((job) => (
            <Button
              key={job.id}
              variant="outline"
              onClick={() => publishMutation.mutate({ content_job_id: job.id, dry_run: true })}
              disabled={publishMutation.isPending}
            >
              Publish {job.id.slice(0, 8)}
            </Button>
          ))}
        </div>
      </Card>

      {jobs.data && jobs.data.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {jobs.data.map((job) => (
            <PublishingStatusCard key={job.id} job={job} />
          ))}
        </div>
      )}

      <Card className="p-6">
        <h2 className="text-lg font-semibold">Published Posts</h2>
        <div className="mt-4 space-y-3">
          {posts.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No published posts yet.</p>
          )}
          {posts.data?.map((post) => (
            <div key={post.id} className="rounded-2xl border border-border bg-muted/40 p-4">
              <p className="font-medium capitalize">{post.platform}</p>
              <p className="text-sm text-muted-foreground">
                {post.external_url ?? "No external URL"}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export default function ContentPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get(TAB_PARAM);
  const activeTab: Tab = isValidTab(rawTab) ? rawTab : "plans";

  function switchTab(tab: Tab) {
    setSearchParams({ [TAB_PARAM]: tab }, { replace: true });
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Content</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage content plans, route approvals, and track publishing.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(v) => switchTab(v as Tab)}>
        <TabsList>
          <TabsTrigger value="plans">Plans &amp; Jobs</TabsTrigger>
          <TabsTrigger value="approvals">Approvals</TabsTrigger>
          <TabsTrigger value="publishing">Publishing</TabsTrigger>
        </TabsList>

        <TabsContent value="plans" className="mt-6">
          <PlansTab />
        </TabsContent>

        <TabsContent value="approvals" className="mt-6">
          <ApprovalsTab />
        </TabsContent>

        <TabsContent value="publishing" className="mt-6">
          <PublishingTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
