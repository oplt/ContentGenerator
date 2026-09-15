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
import { FormField, SectionHelp } from "../components/ui/HelpDisclosure";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { useState } from "react";
import { Badge } from "../components/ui/badge";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { contentJobNeedsPolling, statusAwareRefetchInterval } from "../lib/polling";
import { queryPolicy } from "../lib/queryPolicy";

const DETAIL_TABS = ["content", "assets", "quality", "publishing", "history"] as const;
type DetailTab = (typeof DETAIL_TABS)[number];

export default function ContentDetailPage() {
  const params = useParams();
  const [feedback, setFeedback] = useState("");
  const [groupInstruction, setGroupInstruction] = useState("");
  const [detailTab, setDetailTab] = useDeepLinkTab<DetailTab>("tab", DETAIL_TABS, "content");
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const job = useQuery({
    queryKey: queryKeys.contentJob(tenantId ?? "none", params.id ?? ""),
    queryFn: ({ signal }) => getContentJob(params.id ?? "", { signal }),
    enabled: enabled && Boolean(params.id),
    ...queryPolicy.fast,
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
  const mediaAssets = job.data.assets.filter((asset) => asset.asset_type !== "text_variant");

  return (
    <div className="space-y-6">
      <SectionHelp summary="Revision vs asset-group regenerate">
        Job regenerate revises this run with feedback. Asset-group regenerate rebuilds the package when an
        <code className="mx-1">asset_group_id</code> is present—prefer that for multi-asset consistency.
      </SectionHelp>
      {regenerateMutation.isError || regenerateGroupMutation.isError ? (
        <ErrorState message="Regeneration failed. Review the instruction and try again." />
      ) : null}

      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Content Job</h1>
            <p className="mt-2 text-sm text-muted-foreground">{job.data.stage}</p>
            {job.data.risk_label ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge
                  variant={
                    job.data.risk_label === "blocked"
                      ? "danger"
                      : job.data.risk_label === "high"
                        ? "warning"
                        : "muted"
                  }
                >
                  Risk review: {job.data.risk_label}
                </Badge>
              </div>
            ) : null}
          </div>
          <VideoJobProgress job={job.data} />
        </div>
      </Card>

      <Tabs value={detailTab} onValueChange={(v) => setDetailTab(v as DetailTab)} className="space-y-6">
        <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-5">
          <TabsTrigger value="content">Content</TabsTrigger>
          <TabsTrigger value="assets">Assets</TabsTrigger>
          <TabsTrigger value="quality">Quality</TabsTrigger>
          <TabsTrigger value="publishing">Publishing</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="content" className="space-y-6">
          <ContentVariantTabs assets={job.data.assets} />
          <Card className="p-6">
            <h2 className="text-lg font-semibold">Revision loop</h2>
            <FormField
              className="mt-4"
              label="Revision feedback"
              htmlFor="content-revision-feedback"
              help="Describe what to change. Submitting queues a new generation run."
            >
              <Textarea
                id="content-revision-feedback"
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                placeholder="Give revision feedback"
              />
            </FormField>
            <Button className="mt-4" onClick={() => regenerateMutation.mutate(feedback)}>
              Regenerate
            </Button>
          </Card>
        </TabsContent>

        <TabsContent value="assets" className="space-y-6">
          {assetGroupId ? (
            <Card className="p-6">
              <h2 className="text-lg font-semibold">Asset group regenerate</h2>
              <FormField
                className="mt-4"
                label="Group instruction"
                htmlFor="asset-group-instruction"
                help={`Rebuild package for group ${assetGroupId.slice(0, 8)}…`}
              >
                <Textarea
                  id="asset-group-instruction"
                  value={groupInstruction}
                  onChange={(event) => setGroupInstruction(event.target.value)}
                  placeholder="Instruction for asset-group regenerate"
                />
              </FormField>
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
          ) : (
            <p className="text-sm text-muted-foreground">No asset group linked to this job yet.</p>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {mediaAssets.map((asset) => (
              <Card key={asset.id} className="flex items-center justify-between gap-4 p-5">
                <div>
                  <h3 className="font-medium">{asset.asset_type}</h3>
                  <p className="text-sm text-muted-foreground">{asset.mime_type}</p>
                </div>
                <AssetPreviewDialog asset={asset} />
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="quality" className="space-y-6">
          <Card className="p-6">
            <h2 className="text-lg font-semibold">Risk review</h2>
            {job.data.risk_label ? (
              <Badge
                className="mt-3"
                variant={
                  job.data.risk_label === "blocked"
                    ? "danger"
                    : job.data.risk_label === "high"
                      ? "warning"
                      : "muted"
                }
              >
                {job.data.risk_label}
              </Badge>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">No risk label on this job.</p>
            )}
            {riskWarnings.length > 0 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {riskWarnings.map((warning) => (
                  <Badge key={warning} variant="warning">
                    {warning}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="mt-3 text-sm text-muted-foreground">No risk warnings recorded.</p>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="publishing" className="space-y-6">
          <Card className="p-6">
            <h2 className="text-lg font-semibold">Publish readiness</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Stage <span className="font-medium text-foreground">{job.data.stage}</span> · progress{" "}
              {Math.round(job.data.progress ?? 0)}%
            </p>
            <div className="mt-4">
              <VideoJobProgress job={job.data} />
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="history" className="space-y-6">
          <Card className="p-6">
            <h2 className="text-lg font-semibold">Job history</h2>
            <dl className="mt-4 grid gap-3 text-sm md:grid-cols-2">
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Job ID</dt>
                <dd className="mt-1 font-mono text-xs">{job.data.id}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Stage</dt>
                <dd className="mt-1 font-medium">{job.data.stage}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Started</dt>
                <dd className="mt-1 font-medium">{job.data.started_at ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Completed</dt>
                <dd className="mt-1 font-medium">{job.data.completed_at ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Progress</dt>
                <dd className="mt-1 font-medium">{Math.round(job.data.progress ?? 0)}%</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-muted-foreground">Assets</dt>
                <dd className="mt-1 font-medium">{job.data.assets.length}</dd>
              </div>
            </dl>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
