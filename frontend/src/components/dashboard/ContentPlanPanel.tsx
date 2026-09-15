import type { ContentPlan } from "../../api/content";
import type { SocialAccount } from "../../api/publishing";
import { formatSocialAccountLabel } from "../../lib/socialAccounts";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";

export function ContentPlanPanel({
  plan,
  onGenerate,
  selectedAccounts = [],
  generatePending = false,
}: {
  plan: ContentPlan;
  onGenerate?: () => void;
  selectedAccounts?: SocialAccount[];
  generatePending?: boolean;
}) {
  const planTargets = plan.target_social_account_ids ?? [];
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">Plan</p>
          <h3 className="mt-2 text-lg font-semibold">{plan.content_format.toUpperCase()} strategy</h3>
        </div>
        <Badge variant={plan.safe_to_publish ? "success" : "warning"}>{plan.decision}</Badge>
      </div>
      <div className="mt-4 grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
        <div>Platforms: {plan.target_platforms.join(", ") || "—"}</div>
        <div>Tone: {plan.tone}</div>
        <div>Urgency: {plan.urgency}</div>
        <div>CTA: {plan.recommended_cta ?? "None"}</div>
      </div>
      {selectedAccounts.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-medium text-muted-foreground">Will generate for</p>
          <ul className="mt-2 space-y-1 text-sm">
            {selectedAccounts.map((account) => (
              <li key={account.id}>{formatSocialAccountLabel(account)}</li>
            ))}
          </ul>
        </div>
      ) : planTargets.length > 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Plan stores {planTargets.length} account target{planTargets.length === 1 ? "" : "s"}.
        </p>
      ) : null}
      {onGenerate ? (
        <Button className="mt-5" onClick={onGenerate} disabled={generatePending}>
          {generatePending ? "Generating…" : "Generate Content"}
        </Button>
      ) : null}
    </Card>
  );
}
