import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  approveBrief,
  generateBrief,
  getBriefs,
  rejectBrief,
  regenerateBrief,
  rewriteBrief,
  sendBriefToTelegram,
  type BriefStatus,
} from "../api/briefs";
import { getStoryClusters } from "../api/stories";
import { BriefCard } from "../components/dashboard/BriefCard";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { useTenantScope } from "../hooks/useTenantScope";
import { briefsNeedPolling, statusAwareRefetchInterval } from "../lib/polling";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";

const STATUS_TABS: Array<{ label: string; value: BriefStatus | undefined }> = [
  { label: "All", value: undefined },
  { label: "Ready", value: "ready" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Pending", value: "pending" },
];

type GenerateForm = {
  story_cluster_id: string;
};

export default function EditorialBriefsPage() {
  const [activeStatus, setActiveStatus] = useState<BriefStatus | undefined>(undefined);
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();

  const briefs = useQuery({
    queryKey: queryKeys.briefs(tenantId ?? "none", activeStatus),
    queryFn: ({ signal }) => getBriefs(activeStatus, { signal }),
    enabled,
    refetchInterval: visible ? statusAwareRefetchInterval(15_000, briefsNeedPolling) : false,
  });
  const clusters = useQuery({
    queryKey: queryKeys.stories(tenantId ?? "none"),
    queryFn: getStoryClusters,
    enabled,
  });

  const form = useForm<GenerateForm>();

  const invalidate = () => {
    if (!tenantId) return Promise.resolve();
    return queryClient.invalidateQueries({ queryKey: queryKeys.briefs(tenantId) });
  };

  const generateMutation = useMutation({
    mutationFn: (data: GenerateForm) => generateBrief({ story_cluster_id: data.story_cluster_id }),
    onSuccess: async () => {
      await invalidate();
      form.reset();
    },
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => approveBrief(id, note),
    onSuccess: async () => {
      await invalidate();
      setMutatingId(null);
    },
    onError: () => setMutatingId(null),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => rejectBrief(id, note),
    onSuccess: async () => {
      await invalidate();
      setMutatingId(null);
    },
    onError: () => setMutatingId(null),
  });

  const regenerateMutation = useMutation({
    mutationFn: (id: string) => regenerateBrief(id),
    onSuccess: async () => {
      await invalidate();
      setMutatingId(null);
    },
    onError: () => setMutatingId(null),
  });

  const rewriteMutation = useMutation({
    mutationFn: (id: string) => rewriteBrief(id, { mode: "rewrite" }),
    onSuccess: async () => {
      await invalidate();
      setMutatingId(null);
    },
    onError: () => setMutatingId(null),
  });

  const sendTelegramMutation = useMutation({
    mutationFn: (id: string) => sendBriefToTelegram(id),
    onSuccess: async () => {
      await invalidate();
      setMutatingId(null);
    },
    onError: () => setMutatingId(null),
  });

  const worthyClusters = clusters.data?.filter((cluster) => cluster.worthy_for_content) ?? [];

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Editorial Briefs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Briefs convert approved trend candidates into editorial angles before asset package generation can proceed.
        </p>
        <form
          className="mt-5 flex flex-wrap gap-3 items-end"
          onSubmit={form.handleSubmit((data) => generateMutation.mutate(data))}
        >
          <div className="flex-1 min-w-[240px] space-y-1">
            <label className="text-sm font-medium">Trend candidate</label>
            <select
              aria-label="Select trend candidate"
              className="flex h-11 w-full rounded-xl border border-input bg-card px-3 py-2 text-sm text-foreground shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              {...form.register("story_cluster_id", { required: true })}
            >
              <option value="">— Select a candidate —</option>
              {worthyClusters.map((cluster) => (
                <option key={cluster.id} value={cluster.id}>
                  {cluster.headline.slice(0, 80)} [{cluster.content_vertical}]
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={generateMutation.isPending || worthyClusters.length === 0}>
            {generateMutation.isPending ? "Generating…" : "Generate Brief"}
          </Button>
        </form>
        {worthyClusters.length === 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            No editorially ready trend candidates available. Ingest signals and wait for risk gates to clear.
          </p>
        )}
      </Card>

      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setActiveStatus(tab.value)}
            className={[
              "rounded px-3 py-1 text-sm font-medium transition-colors",
              activeStatus === tab.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/70",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {briefs.isLoading ? (
        <LoadingState label="Loading briefs" />
      ) : !briefs.data || briefs.data.length === 0 ? (
        <EmptyState
          title="No editorial briefs"
          description="Generate a brief from an editorially ready trend candidate above."
        />
      ) : (
        <div className="grid gap-4">
          {briefs.data.map((brief) => (
            <BriefCard
              key={brief.id}
              brief={brief}
              isMutating={mutatingId === brief.id}
              onApprove={(id, note) => {
                setMutatingId(id);
                approveMutation.mutate({ id, note });
              }}
              onReject={(id, note) => {
                setMutatingId(id);
                rejectMutation.mutate({ id, note });
              }}
              onRegenerate={(id) => {
                setMutatingId(id);
                regenerateMutation.mutate(id);
              }}
              onRewrite={(id) => {
                setMutatingId(id);
                rewriteMutation.mutate(id);
              }}
              onSendTelegram={(id) => {
                setMutatingId(id);
                sendTelegramMutation.mutate(id);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
