import type { SocialAccount } from "../../api/publishing";
import { formatSocialAccountLabel, socialAccountStatusVariant } from "../../lib/socialAccounts";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

type SocialAccountSelectorProps = {
  accounts: SocialAccount[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  label?: string;
  description?: string;
  disabled?: boolean;
};

export function SocialAccountSelector({
  accounts,
  selectedIds,
  onChange,
  label = "Publish destinations",
  description = "Select one or more accounts. Same-platform accounts create distinct jobs.",
  disabled = false,
}: SocialAccountSelectorProps) {
  const selected = new Set(selectedIds);

  function toggle(accountId: string) {
    if (disabled) return;
    if (selected.has(accountId)) {
      onChange(selectedIds.filter((id) => id !== accountId));
      return;
    }
    onChange([...selectedIds, accountId]);
  }

  if (accounts.length === 0) {
    return (
      <Card className="p-4">
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          No social accounts connected. Add accounts under Connected Accounts first.
        </p>
      </Card>
    );
  }

  return (
    <fieldset disabled={disabled} className="space-y-3">
      <legend className="text-sm font-semibold">{label}</legend>
      <p className="text-sm text-muted-foreground">{description}</p>
      <div
        className="grid gap-3 sm:grid-cols-2"
        role="group"
        aria-label={label}
      >
        {accounts.map((account) => {
          const isSelected = selected.has(account.id);
          const inputId = `social-account-${account.id}`;
          return (
            <label
              key={account.id}
              htmlFor={inputId}
              className={`flex cursor-pointer items-start gap-3 rounded-2xl border p-4 transition ${
                isSelected ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40"
              } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
            >
              <input
                id={inputId}
                type="checkbox"
                className="mt-1 h-4 w-4 accent-primary"
                checked={isSelected}
                onChange={() => toggle(account.id)}
                disabled={disabled || account.status === "quarantined"}
                aria-describedby={`${inputId}-meta`}
              />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-medium capitalize">{account.platform}</span>
                  <Badge variant={socialAccountStatusVariant(account.status)}>{account.status}</Badge>
                  {account.metadata.mode ? (
                    <Badge variant={account.metadata.mode === "stub" ? "warning" : "muted"}>
                      {account.metadata.mode}
                    </Badge>
                  ) : null}
                </span>
                <span id={`${inputId}-meta`} className="mt-1 block text-sm text-muted-foreground">
                  {formatSocialAccountLabel(account)}
                </span>
                {Object.keys(account.capability_flags ?? {}).length > 0 ? (
                  <span className="mt-2 flex flex-wrap gap-1">
                    {Object.entries(account.capability_flags)
                      .slice(0, 4)
                      .map(([key, value]) => (
                        <span key={key} className="rounded-md border px-1.5 py-0.5 text-[11px] text-muted-foreground">
                          {key}:{value}
                        </span>
                      ))}
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {selectedIds.length === 0
          ? "No accounts selected — publish will use stored job targets or legacy platform lookup."
          : `${selectedIds.length} account${selectedIds.length === 1 ? "" : "s"} selected`}
      </p>
    </fieldset>
  );
}
