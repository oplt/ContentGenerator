import { useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import type { BriefStatus, EditorialBrief } from "../../api/briefs";

const STATUS_VARIANT: Record<BriefStatus, "default" | "muted" | "success" | "warning" | "danger"> = {
  pending: "muted",
  generating: "muted",
  ready: "warning",
  approved: "success",
  rejected: "danger",
  expired: "muted",
};

export type BriefCardProps = {
  brief: EditorialBrief;
  onApprove: (id: string, note?: string) => void;
  onReject: (id: string, note: string) => void;
  onRegenerate: (id: string) => void;
  onRewrite: (id: string) => void;
  onSendTelegram: (id: string) => void;
  isMutating: boolean;
};

export function BriefCard({
  brief,
  onApprove,
  onReject,
  onRegenerate,
  onRewrite,
  onSendTelegram,
  isMutating,
}: BriefCardProps) {
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
            <Badge variant="muted" className="capitalize">
              {brief.content_vertical}
            </Badge>
            <Badge
              variant={
                brief.risk_level === "safe"
                  ? "default"
                  : brief.risk_level === "unsafe"
                    ? "danger"
                    : "warning"
              }
            >
              {brief.risk_level}
            </Badge>
          </div>
          <h2 className="font-semibold text-lg leading-tight">{brief.headline}</h2>
          <p className="mt-1 text-sm text-muted-foreground italic">{brief.angle}</p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          {brief.status === "ready" && (
            <>
              <Button size="sm" disabled={isMutating} onClick={() => onApprove(brief.id)}>
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={isMutating}
                onClick={() => setShowActions(!showActions)}
              >
                Reject
              </Button>
              <Button size="sm" variant="outline" disabled={isMutating} onClick={() => onRewrite(brief.id)}>
                Rewrite
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={isMutating}
                onClick={() => onSendTelegram(brief.id)}
              >
                Send Telegram
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
        <span>
          Format:{" "}
          <span className="text-foreground font-medium capitalize">{brief.recommended_format}</span>
        </span>
        <span>
          Platforms:{" "}
          <span className="text-foreground font-medium">
            {brief.target_platforms.join(", ") || "—"}
          </span>
        </span>
        <span>
          Tone: <span className="text-foreground font-medium">{brief.tone_guidance}</span>
        </span>
        {brief.expires_at && (
          <span>
            Expires:{" "}
            <span className="text-foreground font-medium">
              {new Date(brief.expires_at).toLocaleDateString()}
            </span>
          </span>
        )}
        {brief.operator_note && (
          <span className="w-full">
            Note: <span className="text-foreground">{brief.operator_note}</span>
          </span>
        )}
        {brief.risk_notes && <span className="w-full text-warning">Risk: {brief.risk_notes}</span>}
      </div>
    </Card>
  );
}
