import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import type { StoryCluster } from "../../api/stories";
import { createContentPlan, generateContent } from "../../api/content";
import { queryClient } from "../../lib/queryClient";
import { Card } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { TrendScoreBadge } from "./TrendScoreBadge";

export function StoryClusterCard({ cluster }: { cluster: StoryCluster }) {
  const navigate = useNavigate();

  const planAndGenerate = useMutation({
    mutationFn: async () => {
      const plan = await createContentPlan({ story_cluster_id: cluster.id });
      const job = await generateContent(plan.id);
      return job;
    },
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: ["content"] });
      navigate(`/dashboard/content/${job.id}`);
    },
  });

  return (
    <Card className="group h-full p-5 transition hover:border-primary/40">
      <Link to={`/dashboard/stories/${cluster.id}`} className="block">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{cluster.primary_topic}</p>
            <h3 className="mt-2 text-lg font-semibold leading-tight">{cluster.headline}</h3>
          </div>
          <TrendScoreBadge score={cluster.latest_trend_score} />
        </div>
        <p className="mt-3 text-sm text-muted-foreground">{cluster.summary}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Badge variant={cluster.worthy_for_content ? "success" : "muted"}>
            {cluster.worthy_for_content ? "Generate" : cluster.awaiting_confirmation ? "Awaiting Tier 1" : "Hold"}
          </Badge>
          <Badge variant="muted" className="capitalize">
            {cluster.workflow_state.replace(/_/g, " ")}
          </Badge>
          <Badge variant={cluster.risk_level === "safe" ? "default" : cluster.risk_level === "unsafe" ? "danger" : "warning"}>
            {cluster.risk_level}
          </Badge>
          {cluster.content_vertical && cluster.content_vertical !== "general" && (
            <Badge variant="muted" className="capitalize">{cluster.content_vertical}</Badge>
          )}
          {cluster.tier1_sources_confirmed > 0 && (
            <Badge variant="muted">T1: {cluster.tier1_sources_confirmed}</Badge>
          )}
        </div>
        {cluster.block_reason && (
          <p className="mt-2 text-xs text-destructive">{cluster.block_reason.replace(/_/g, " ")}</p>
        )}
      </Link>
      {cluster.worthy_for_content && (
        <div className="mt-4 border-t border-border pt-4">
          <Button
            size="sm"
            className="w-full"
            disabled={planAndGenerate.isPending}
            onClick={(e) => {
              e.preventDefault();
              planAndGenerate.mutate();
            }}
          >
            {planAndGenerate.isPending ? "Creating…" : "Plan & Generate"}
          </Button>
        </div>
      )}
    </Card>
  );
}
