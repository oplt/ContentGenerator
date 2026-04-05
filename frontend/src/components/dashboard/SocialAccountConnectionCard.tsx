import type { SocialAccount } from "../../api/publishing";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

export function SocialAccountConnectionCard({ account }: { account: SocialAccount }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{account.platform}</p>
          <h3 className="mt-2 text-lg font-semibold">{account.display_name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{account.handle ?? "No handle configured"}</p>
        </div>
        <Badge variant={account.metadata.mode === "stub" ? "warning" : "success"}>
          {account.metadata.mode ?? account.status}
        </Badge>
      </div>
    </Card>
  );
}
