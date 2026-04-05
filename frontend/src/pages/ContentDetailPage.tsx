import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { regenerateContent, getContentJob } from "../api/content";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Textarea } from "../components/ui/textarea";
import { ContentVariantTabs } from "../components/dashboard/ContentVariantTabs";
import { VideoJobProgress } from "../components/dashboard/VideoJobProgress";
import { AssetPreviewDialog } from "../components/dashboard/AssetPreviewDialog";
import { LoadingState } from "../components/ui/LoadingState";
import { useState } from "react";

export default function ContentDetailPage() {
  const params = useParams();
  const [feedback, setFeedback] = useState("");
  const job = useQuery({
    queryKey: ["content", "job", params.id],
    queryFn: () => getContentJob(params.id ?? ""),
    enabled: Boolean(params.id),
    refetchInterval: 10_000,
  });
  const regenerateMutation = useMutation({
    mutationFn: (value: string) => regenerateContent(params.id ?? "", value),
  });

  if (job.isLoading || !job.data) {
    return <LoadingState label="Loading content job" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Content Job</h1>
            <p className="mt-2 text-sm text-muted-foreground">{job.data.stage}</p>
          </div>
          <VideoJobProgress job={job.data} />
        </div>
      </Card>
      <ContentVariantTabs assets={job.data.assets} />
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Revision Loop</h2>
        <Textarea className="mt-4" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Give revision feedback" />
        <Button className="mt-4" onClick={() => regenerateMutation.mutate(feedback)}>Regenerate</Button>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {job.data.assets.filter((asset) => asset.asset_type !== "text_variant").map((asset) => (
          <Card key={asset.id} className="flex items-center justify-between gap-4 p-5">
            <div>
              <h3 className="font-medium">{asset.asset_type}</h3>
              <p className="text-sm text-muted-foreground">{asset.mime_type}</p>
            </div>
            <AssetPreviewDialog asset={asset} />
          </Card>
        ))}
      </div>
    </div>
  );
}
