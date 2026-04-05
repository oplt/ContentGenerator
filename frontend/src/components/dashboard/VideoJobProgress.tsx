import type { ContentJob } from "../../api/content";

export function VideoJobProgress({ job }: { job: ContentJob }) {
  return (
    <div className="space-y-2 rounded-[1.5rem] border border-border bg-card p-4">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">Video Pipeline</span>
        <span className="text-muted-foreground">{job.stage}</span>
      </div>
      <div className="h-2 rounded-full bg-muted">
        <div
          className="h-2 rounded-full bg-primary transition-all"
          style={{ width: `${job.progress}%` }}
        />
      </div>
    </div>
  );
}
