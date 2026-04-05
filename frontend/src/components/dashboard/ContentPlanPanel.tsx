import type { ContentPlan } from "../../api/content";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";

export function ContentPlanPanel({
  plan,
  onGenerate,
}: {
  plan: ContentPlan;
  onGenerate?: () => void;
}) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Plan</p>
          <h3 className="mt-2 text-lg font-semibold">{plan.content_format.toUpperCase()} strategy</h3>
        </div>
        <Badge variant={plan.safe_to_publish ? "success" : "warning"}>{plan.decision}</Badge>
      </div>
      <div className="mt-4 grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
        <div>Platforms: {plan.target_platforms.join(", ")}</div>
        <div>Tone: {plan.tone}</div>
        <div>Urgency: {plan.urgency}</div>
        <div>CTA: {plan.recommended_cta ?? "None"}</div>
      </div>
      {onGenerate ? (
        <Button className="mt-5" onClick={onGenerate}>
          Generate Content
        </Button>
      ) : null}
    </Card>
  );
}
