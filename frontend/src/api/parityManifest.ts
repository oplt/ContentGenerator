/**
 * Phase 8 — Backend ↔ frontend feature parity contract.
 */
import { PARITY_OPERATIONS } from "./parityInventory";
import {
  operationKey,
  type ParityCategory,
  type ParityOperation,
} from "./parityTypes";

export type { ParityCategory, ParityOperation };
export { PARITY_CATEGORIES, operationKey } from "./parityTypes";
export { PARITY_OPERATIONS } from "./parityInventory";

/** Curated USER_FACING_UI subset kept for focused regression spot-checks. */
export const REQUIRED_PARITY: readonly ParityOperation[] = PARITY_OPERATIONS.filter(
  (op) =>
    op.category === "USER_FACING_UI" &&
    [
      "POST /api/v1/auth/mfa/enable",
      "POST /api/v1/auth/mfa/verify",
      "POST /api/v1/auth/mfa/disable",
      "GET /api/v1/users/me",
      "POST /api/v1/briefs/{brief_id}/rewrite",
      "POST /api/v1/briefs/{brief_id}/send-telegram",
      "POST /api/v1/content/asset-groups/{asset_group_id}/regenerate",
      "GET /api/v1/stories/candidates/{candidate_id}",
    ].includes(operationKey(op)),
);

export const UI_EXEMPT_PREFIXES = [
  "/api/v1/health",
  "/api/v1/approvals/telegram/webhook",
  "/api/v1/approvals/whatsapp/webhook",
  "/api/v1/ws",
] as const;

export const CANONICAL_STORY_PREFIX = "/api/v1/stories";
export const DEPRECATED_TRENDS_PREFIX = "/api/v1/trends";

export function operationsByCategory(category: ParityCategory): ParityOperation[] {
  return PARITY_OPERATIONS.filter((op) => op.category === category);
}
