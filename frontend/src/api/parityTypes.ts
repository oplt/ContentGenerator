/**
 * Phase 8 — Backend ↔ frontend feature parity classification.
 */

export const PARITY_CATEGORIES = [
  "USER_FACING_UI",
  "FRONTEND_INTERNAL",
  "WEBHOOK",
  "WORKER_INTERNAL",
  "HEALTH_OBSERVABILITY",
  "MACHINE_ONLY",
  "INTENTIONALLY_NO_UI",
] as const;

export type ParityCategory = (typeof PARITY_CATEGORIES)[number];

export type ParityOperation = {
  method: string;
  path: string;
  category: ParityCategory;
  /** `relative/path.ts#exportSymbol` for typed API clients (or telemetry entrypoints). */
  client?: string;
  /** Relative path under `frontend/src` for the owning UI surface. */
  ui?: string;
  /** Required for every non-USER_FACING_UI classification. */
  exemptionReason?: string;
};

export function operationKey(op: Pick<ParityOperation, "method" | "path">): string {
  return `${op.method.toUpperCase()} ${op.path}`;
}
