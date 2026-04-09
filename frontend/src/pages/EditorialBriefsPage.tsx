import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  approveBrief,
  generateBrief,
  getBriefs,
  rejectBrief,
  regenerateBrief,
  type BriefStatus,
  type EditorialBrief,
} from "../api/briefs";
import { getStoryClusters } from "../api/stories";
import { queryClient } from "../lib/queryClient";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";

const STATUS_VARIANT: Record<BriefStatus, "default" | "muted" | "success" | "warning" | "danger"> = {
  pending: "muted",
  generating: "muted",
  ready: "warning",
  approved: "success",
  rejected: "danger",
  expired: "muted",
};

const STATUS_TABS: Array<{ label: string; value: BriefStatus | undefined }> = [
  { label: "All", value: undefined },
  { label: "Ready", value: "ready" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Pending", value: "pending" },
];

function BriefCard({
  brief,
  onApprove,
  onReject,
  onRegenerate,
  isMutating,
}: {
  brief: EditorialBrief;
  onApprove: (id: string, note?: string) => void;
  onReject: (id: string, note: string) => void;
  onRegenerate: (id: string) => void;
  isMutating: boolean;
}) {
  const [showActions, setShowActions] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <Badge variant={STATUS_VARIANT[brief.status as BriefStatus] ?? "muted"}>
              {brief.status}
            </Badge>
            <Badge variant="muted" className="capitalize">{brief.content_vertical}</Badge>
            <Badge variant={brief.risk_level === "safe" ? "default" : brief.risk_level === "unsafe" ? "danger" : "warning"}>
              {brief.risk_level}
            </Badge>
          </div>
          <h2 className="font-semibold text-lg leading-tight">{brief.headline}</h2>
          <p className="mt-1 text-sm text-muted-foreground italic">{brief.angle}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          {brief.status === "ready" && (
            <>
              <Button size="sm" disabled={isMutating} onClick={() => onApprove(brief.id)}>
                Approve
              </Button>
              <Button size="sm" variant="outline" disabled={isMutating} onClick={() => setShowActions(!showActions)}>
                Reject
              </Button>
            </>
          )}
          {(brief.status === "rejected" || brief.status === "expired" || brief.status === "ready") && (
            <Button size="sm" variant="outline" disabled={isMutating} onClick={() => onRegenerate(brief.id)}>
              Regenerate
            </Button>
          )}
        </div>
      </div>

      {showActions && brief.status === "ready" && (
        <div className="flex gap-2">
          <Input
            placeholder="Rejection reason (required)"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            className="flex-1"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!rejectNote.trim() || isMutating}
            onClick={() => {
              onReject(brief.id, rejectNote);
              setShowActions(false);
              setRejectNote("");
            }}
          >
            Confirm Reject
          </Button>
        </div>
      )}

      {brief.talking_points.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground mb-2">Talking Points</p>
          <ul className="space-y-1">
            {brief.talking_points.map((point, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <span className="text-muted-foreground shrink-0">{i + 1}.</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground border-t border-border pt-3">
        <span>Format: <span className="text-foreground font-medium capitalize">{brief.recommended_format}</span></span>
        <span>Platforms: <span className="text-foreground font-medium">{brief.target_platforms.join(", ") || "—"}</span></span>
        <span>Tone: <span className="text-foreground font-medium">{brief.tone_guidance}</span></span>
        {brief.expires_at && (
          <span>Expires: <span className="text-foreground font-medium">{new Date(brief.expires_at).toLocaleDateString()}</span></span>
        )}
        {brief.operator_note && (
          <span className="w-full">Note: <span className="text-foreground">{brief.operator_note}</span></span>
        )}
        {brief.risk_notes && (
          <span className="w-full text-warning">Risk: {brief.risk_notes}</span>
        )}
      </div>
    </Card>
  );
}

type GenerateForm = {
  story_cluster_id: string;
};

export default function EditorialBriefsPage() {
  const [activeStatus, setActiveStatus] = useState<BriefStatus | undefined>(undefined);
  const [mutatingId, setMutatingId] = useState<string | null>(null);

  const briefs = useQuery({
    queryKey: ["briefs", activeStatus],
    queryFn: () => getBriefs(activeStatus),
    refetchInterval: 15_000,
  });
  const clusters = useQuery({ queryKey: ["stories"], queryFn: getStoryClusters });

  const form = useForm<GenerateForm>();

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["briefs"] });

  const generateMutation = useMutation({
    mutationFn: (data: GenerateForm) => generateBrief({ story_cluster_id: data.story_cluster_id }),
    onSuccess: async () => { await invalidate(); form.reset(); },
  });

  const approveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) => approveBrief(id, note),
    onSuccess: async () => { await invalidate(); setMutatingId(null); },
    onError: () => setMutatingId(null),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => rejectBrief(id, note),
    onSuccess: async () => { await invalidate(); setMutatingId(null); },
    onError: () => setMutatingId(null),
  });

  const regenerateMutation = useMutation({
    mutationFn: (id: string) => regenerateBrief(id),
    onSuccess: async () => { await invalidate(); setMutatingId(null); },
    onError: () => setMutatingId(null),
  });

  const worthyClusters = clusters.data?.filter((c) => c.worthy_for_content) ?? [];

  return (
    <div className="space-y-6">
      {/* Generate new brief */}
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
              {worthyClusters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.headline.slice(0, 80)} [{c.content_vertical}]
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

      {/* Status filter tabs */}
      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            onClick={() => setActiveStatus(tab.value)}
            className={[
              "rounded-full px-3 py-1 text-sm font-medium transition-colors",
              activeStatus === tab.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/70",
            ].join(" ")}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Brief list */}
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
            />
          ))}
        </div>
      )}
    </div>
  );
}
