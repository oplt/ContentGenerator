import type { PublishingJob } from "../../api/publishing";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

export function PublishingStatusCard({ job }: { job: PublishingJob }) {
  const variant =
    job.status === "succeeded" ? "success" : job.status === "manual_required" ? "warning" : "muted";
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{job.platform}</p>
          <h3 className="mt-2 text-base font-semibold">{job.idempotency_key}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{job.external_post_url ?? "Awaiting provider URL"}</p>
        </div>
        <Badge variant={variant}>{job.status}</Badge>
      </div>
    </Card>
  );
}
