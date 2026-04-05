import type { ApprovalRequest } from "../../api/approvals";
import { Badge } from "../ui/badge";

export function ApprovalTimeline({ approval }: { approval: ApprovalRequest }) {
  return (
    <div className="space-y-3">
      {approval.messages.map((message) => (
        <div key={message.id} className="rounded-2xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <Badge variant={message.direction === "inbound" ? "default" : "muted"}>
              {message.direction}
            </Badge>
            <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {message.parsed_intent}
            </span>
          </div>
          <p className="mt-3 text-sm text-muted-foreground">{message.raw_text}</p>
        </div>
      ))}
    </div>
  );
}
