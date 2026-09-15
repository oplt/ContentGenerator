/**
 * Curated API ↔ UI parity contract (T5.1).
 * required: product-facing capability with a frontend owner
 * ui_exempt: backend-only / internal (webhooks, workers, health plumbing)
 */
export type ParityOwner =
  | "auth"
  | "users"
  | "stories"
  | "briefs"
  | "content"
  | "settings"
  | "publishing"
  | "analytics"
  | "approvals"
  | "sources"
  | "audit"
  | "trending-repos"
  | "ui_exempt";

export type ParityEntry = {
  method: string;
  path: string;
  owner: ParityOwner;
  client?: string;
  ui?: string;
  notes?: string;
};

export const REQUIRED_PARITY: ParityEntry[] = [
  { method: "POST", path: "/api/v1/auth/mfa/enable", owner: "auth", client: "api/auth.ts#enableMfa", ui: "pages/MfaSetupPage.tsx" },
  { method: "POST", path: "/api/v1/auth/mfa/verify", owner: "auth", client: "api/auth.ts#verifyMfa", ui: "pages/MfaSetupPage.tsx" },
  { method: "POST", path: "/api/v1/auth/mfa/disable", owner: "auth", client: "api/auth.ts#disableMfa", ui: "pages/AccountSecurityPage.tsx" },
  { method: "GET", path: "/api/v1/users/me", owner: "users", client: "api/users.ts#getMyProfile", ui: "pages/AccountSecurityPage.tsx" },
  { method: "PATCH", path: "/api/v1/users/me", owner: "users", client: "api/users.ts#updateMyProfile", ui: "pages/AccountSecurityPage.tsx" },
  { method: "PATCH", path: "/api/v1/users/me/password", owner: "users", client: "api/users.ts#changeMyPassword", ui: "pages/AccountSecurityPage.tsx" },
  { method: "GET", path: "/api/v1/stories/candidates/{candidate_id}", owner: "stories", client: "api/stories.ts#getTrendCandidate", ui: "pages/StoryDetailPage.tsx" },
  { method: "POST", path: "/api/v1/briefs/{brief_id}/rewrite", owner: "briefs", client: "api/briefs.ts#rewriteBrief", ui: "pages/EditorialBriefsPage.tsx" },
  { method: "POST", path: "/api/v1/briefs/{brief_id}/send-telegram", owner: "briefs", client: "api/briefs.ts#sendBriefToTelegram", ui: "pages/EditorialBriefsPage.tsx" },
  {
    method: "POST",
    path: "/api/v1/content/asset-groups/{asset_group_id}/regenerate",
    owner: "content",
    client: "api/content.ts#regenerateAssetGroup",
    ui: "pages/ContentDetailPage.tsx",
  },
];

export const UI_EXEMPT_PREFIXES = [
  "/api/v1/health",
  "/api/v1/ws",
  "/api/v1/approvals/whatsapp/webhook",
  "/api/v1/approvals/telegram/webhook",
] as const;

/** Canonical story routes; /trends is a deprecation shim only. */
export const CANONICAL_STORY_PREFIX = "/api/v1/stories";
export const DEPRECATED_TRENDS_PREFIX = "/api/v1/trends";
