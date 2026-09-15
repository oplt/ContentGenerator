import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { regenerateAssetGroup, regenerateContent, getContentJob } from "../api/content";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Textarea } from "../components/ui/textarea";
import { ContentVariantTabs } from "../components/dashboard/ContentVariantTabs";
import { VideoJobProgress } from "../components/dashboard/VideoJobProgress";
import { AssetPreviewDialog } from "../components/dashboard/AssetPreviewDialog";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { HelpDisclosure } from "../components/ui/HelpDisclosure";
import { useState } from "react";
import { Badge } from "../components/ui/badge";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { contentJobNeedsPolling, statusAwareRefetchInterval } from "../lib/polling";

export default function ContentDetailPage() {
  const params = useParams();
  const [feedback, setFeedback] = useState("");
  const [groupInstruction, setGroupInstruction] = useState("");
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const job = useQuery({
    queryKey: queryKeys.contentJob(tenantId ?? "none", params.id ?? ""),
    queryFn: ({ signal }) => getContentJob(params.id ?? "", { signal }),
    enabled: enabled && Boolean(params.id),
    refetchInterval: visible
      ? statusAwareRefetchInterval(10_000, contentJobNeedsPolling)
      : false,
  });
  const regenerateMutation = useMutation({
    mutationFn: (value: string) => regenerateContent(params.id ?? "", value),
    onSuccess: async (result) => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentJob(tenantId, result.id) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentJobs(tenantId) });
    },
  });
  const regenerateGroupMutation = useMutation({
    mutationFn: ({ assetGroupId, instruction }: { assetGroupId: string; instruction: string }) =>
      regenerateAssetGroup(assetGroupId, instruction),
    onSuccess: async (result) => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentJob(tenantId, result.id) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentJobs(tenantId) });
    },
  });

  if (job.isPending && !job.data) {
    return <LoadingState label="Loading content job" />;
  }
  if (job.isError || !job.data) {
    return (
      <ErrorState
        message="This content job could not be loaded."
        onRetry={() => {
          void job.refetch();
        }}
      />
    );
  }

  const riskWarnings = Array.isArray(job.data.risk_review?.warnings)
    ? (job.data.risk_review.warnings as string[])
    : [];
  const assetGroupId =
    job.data.asset_group_id ??
    job.data.assets.find((asset) => asset.asset_group_id)?.asset_group_id ??
    null;

  return (
    <div className="space-y-6">
      <HelpDisclosure summary="Revision vs asset-group regenerate">
        Job regenerate revises this run with feedback. Asset-group regenerate rebuilds the package when an
        <code className="mx-1">asset_group_id</code> is present—prefer that for multi-asset consistency.
      </HelpDisclosure>
      {regenerateMutation.isError || regenerateGroupMutation.isError ? (
        <ErrorState message="Regeneration failed. Review the instruction and try again." />
      ) : null}
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Content Job</h1>
            <p className="mt-2 text-sm text-muted-foreground">{job.data.stage}</p>
            {job.data.risk_label && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant={job.data.risk_label === "blocked" ? "danger" : job.data.risk_label === "high" ? "warning" : "muted"}>
                  Risk review: {job.data.risk_label}
                </Badge>
              </div>
            )}
          </div>
          <VideoJobProgress job={job.data} />
        </div>
      </Card>
      {riskWarnings.length > 0 && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Risk Review</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {riskWarnings.map((warning) => (
              <Badge key={warning} variant="warning">{warning}</Badge>
            ))}
          </div>
        </Card>
      )}
      <ContentVariantTabs assets={job.data.assets} />
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Revision Loop</h2>
        <Textarea className="mt-4" value={feedback} onChange={(event) => setFeedback(event.target.value)} placeholder="Give revision feedback" />
        <Button className="mt-4" onClick={() => regenerateMutation.mutate(feedback)}>Regenerate</Button>
      </Card>
      {assetGroupId ? (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Asset group regenerate</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Rebuild the package for asset group {assetGroupId.slice(0, 8)}… with operator instructions.
          </p>
          <Textarea
            className="mt-4"
            value={groupInstruction}
            onChange={(event) => setGroupInstruction(event.target.value)}
            placeholder="Instruction for asset-group regenerate"
          />
          <Button
            className="mt-4"
            disabled={!groupInstruction.trim() || regenerateGroupMutation.isPending}
            onClick={() =>
              regenerateGroupMutation.mutate({
                assetGroupId,
                instruction: groupInstruction.trim(),
              })
            }
          >
            {regenerateGroupMutation.isPending ? "Regenerating…" : "Regenerate asset group"}
          </Button>
        </Card>
      ) : null}
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
