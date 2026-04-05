import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { createSource, getRawArticles, getSourceHealth, getSources, triggerIngestion } from "../api/sources";
import { queryClient } from "../lib/queryClient";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";
import { SourceHealthTable } from "../components/dashboard/SourceHealthTable";

type SourceForm = {
  name: string;
  url: string;
  source_type: string;
  category: string;
};

export default function SourcesPage() {
  const form = useForm<SourceForm>({ defaultValues: { source_type: "rss", category: "technology" } });
  const sources = useQuery({ queryKey: ["sources"], queryFn: getSources });
  const health = useQuery({ queryKey: ["sources", "health"], queryFn: getSourceHealth });
  const rawArticles = useQuery({ queryKey: ["sources", "articles"], queryFn: getRawArticles });

  const createMutation = useMutation({
    mutationFn: createSource,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
  const ingestMutation = useMutation({
    mutationFn: triggerIngestion,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["sources", "articles"] }),
        queryClient.invalidateQueries({ queryKey: ["stories"] }),
      ]);
    },
  });

  if (sources.isLoading || health.isLoading) {
    return <LoadingState label="Loading sources" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Sources</h1>
        <form
          className="mt-5 grid gap-3 md:grid-cols-5"
          onSubmit={form.handleSubmit(async (values) => {
            await createMutation.mutateAsync({
              ...values,
              parser_type: "auto",
              trust_score: 0.7,
              polling_interval_minutes: 30,
              config: {},
              active: true,
            });
            form.reset({ source_type: "rss", category: "technology" });
          })}
        >
          <Input placeholder="Name" {...form.register("name")} />
          <Input placeholder="URL" {...form.register("url")} />
          <Input placeholder="Type (rss/web/api/sitemap)" {...form.register("source_type")} />
          <Input placeholder="Category" {...form.register("category")} />
          <Button type="submit">Create Source</Button>
        </form>
      </Card>
      {sources.data && sources.data.length > 0 ? (
        <>
          <SourceHealthTable sources={sources.data} health={health.data ?? []} />
          <div className="grid gap-4">
            {sources.data.map((source) => (
              <Card key={source.id} className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="font-semibold">{source.name}</h2>
                  <p className="text-sm text-muted-foreground">{source.url}</p>
                </div>
                <Button onClick={() => ingestMutation.mutate(source.id)}>Ingest Now</Button>
              </Card>
            ))}
          </div>
          <Card className="p-5">
            <h2 className="text-lg font-semibold">Latest Raw Articles</h2>
            <div className="mt-4 space-y-3">
              {rawArticles.data?.slice(0, 8).map((article) => (
                <div key={article.id} className="rounded-2xl border border-border bg-muted/40 p-4">
                  <p className="font-medium">{article.title}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{article.summary}</p>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : (
        <EmptyState title="No sources configured" description="Create your first RSS, API, web, or sitemap source." />
      )}
    </div>
  );
}
