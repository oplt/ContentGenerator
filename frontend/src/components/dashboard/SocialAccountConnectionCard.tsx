import type { SocialAccount } from "../../api/publishing";
import { formatSocialAccountLabel, socialAccountStatusVariant } from "../../lib/socialAccounts";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";

type SocialAccountConnectionCardProps = {
 account: SocialAccount;
 selected?: boolean;
 onSelectToggle?: (accountId: string) => void;
 onValidate?: (connectedAccountId: string) => void;
 connectedAccountId?: string | null;
 validatePending?: boolean;
};

export function SocialAccountConnectionCard({
 account,
 selected = false,
 onSelectToggle,
 onValidate,
 connectedAccountId,
 validatePending = false,
}: SocialAccountConnectionCardProps) {
 return (
 <Card
 className={`p-5 ${selected ? "border-primary bg-primary/5" : ""}`}
 data-account-id={account.id}
 >
 <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
 <div className="min-w-0 flex-1">
 <div className="flex flex-wrap items-center gap-2">
 <p className="text-xs font-medium text-muted-foreground">{account.platform}</p>
 <Badge variant={socialAccountStatusVariant(account.status)}>{account.status}</Badge>
 <Badge variant={account.metadata.mode === "stub" ? "warning" : "success"}>
 {account.metadata.mode ?? account.auth_type ?? "oauth"}
 </Badge>
 </div>
 <h3 className="mt-2 text-lg font-semibold">{account.display_name}</h3>
 <p className="mt-1 text-sm text-muted-foreground">{formatSocialAccountLabel(account)}</p>
 <p className="mt-1 font-mono text-xs text-muted-foreground">id {account.id.slice(0, 8)}</p>
 {account.quarantine_reason ? (
 <p className="mt-2 text-xs text-destructive">{account.quarantine_reason}</p>
 ) : null}
 {Object.keys(account.capability_flags ?? {}).length > 0 ? (
 <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
 {Object.entries(account.capability_flags).map(([key, value]) => (
 <span key={key} className="rounded border px-2 py-1">
 {key}: {value}
 </span>
 ))}
 </div>
 ) : null}
 </div>
 <div className="flex flex-wrap gap-2">
 {onSelectToggle ? (
 <Button
 variant={selected ? "default" : "outline"}
 onClick={() => onSelectToggle(account.id)}
 aria-pressed={selected}
 >
 {selected ? "Selected" : "Select"}
 </Button>
 ) : null}
 {onValidate && connectedAccountId ? (
 <Button
 variant="outline"
 onClick={() => onValidate(connectedAccountId)}
 disabled={validatePending}
 >
 Validate Auth
 </Button>
 ) : null}
 </div>
 </div>
 </Card>
 );
}
