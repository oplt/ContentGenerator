import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getStoryClusters } from "../api/stories";
import { FilterBar } from "../components/dashboard/FilterBar";
import { StoryClusterCard } from "../components/dashboard/StoryClusterCard";
import { LoadingState } from "../components/ui/LoadingState";

export default function StoriesPage() {
  const [query, setQuery] = useState("");
  const stories = useQuery({ queryKey: ["stories"], queryFn: getStoryClusters });
  const filtered = useMemo(
    () =>
      (stories.data ?? []).filter((cluster) =>
        `${cluster.headline} ${cluster.primary_topic}`.toLowerCase().includes(query.toLowerCase())
      ),
    [query, stories.data]
  );

  if (stories.isLoading) {
    return <LoadingState label="Loading trend candidates" />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Trend Candidates</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Review scored topics before they move into editorial briefs and asset generation.
        </p>
      </div>
      <FilterBar value={query} onChange={setQuery} />
      <div className="grid gap-4 xl:grid-cols-3">
        {filtered.map((cluster) => (
          <StoryClusterCard key={cluster.id} cluster={cluster} />
        ))}
      </div>
    </div>
  );
}
