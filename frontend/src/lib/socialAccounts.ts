import type { SocialAccount } from "../api/publishing";

export function formatSocialAccountLabel(account: Pick<SocialAccount, "display_name" | "handle" | "platform">) {
  const identity = account.handle?.trim() || account.display_name;
  return `${account.platform} · ${identity}`;
}

export function socialAccountStatusVariant(
  status: string
): "default" | "success" | "warning" | "muted" | "danger" {
  if (status === "connected" || status === "active") return "success";
  if (status === "needs_reauth") return "warning";
  if (status === "quarantined" || status === "disconnected") return "danger";
  return "muted";
}

export function findAccount(
  accounts: SocialAccount[] | undefined,
  socialAccountId: string | null | undefined
): SocialAccount | undefined {
  if (!socialAccountId || !accounts) return undefined;
  return accounts.find((account) => account.id === socialAccountId);
}
