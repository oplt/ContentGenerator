import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { createContentPlan } from "../api/content";
import { getStoryCluster } from "../api/stories";
import { queryClient } from "../lib/queryClient";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function StoryDetailPage() {
  const params = useParams();
  const story = useQuery({
    queryKey: ["stories", params.id],
    queryFn: () => getStoryCluster(params.id ?? ""),
    enabled: Boolean(params.id),
  });
  const planMutation = useMutation({
    mutationFn: createContentPlan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["content", "plans"] });
    },
  });

  if (story.isLoading || !story.data) {
    return <LoadingState label="Loading story detail" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{story.data.primary_topic}</p>
            <h1 className="mt-3 text-3xl font-semibold">{story.data.headline}</h1>
            <p className="mt-4 max-w-3xl text-sm text-muted-foreground">{story.data.summary}</p>
          </div>
          <Button onClick={() => planMutation.mutate({ story_cluster_id: story.data!.id })}>Create Content Plan</Button>
        </div>
      </Card>
      <div className="grid gap-4">
        {story.data.articles.map((article) => (
          <Card key={article.id} className="p-5">
            <h2 className="font-semibold">{article.title}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{article.summary}</p>
            <a className="mt-3 inline-block text-sm text-primary" href={article.canonical_url} target="_blank" rel="noreferrer">
              Open source
            </a>
          </Card>
        ))}
      </div>
    </div>
  );
}
