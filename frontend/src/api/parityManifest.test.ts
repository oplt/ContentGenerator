import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  CANONICAL_STORY_PREFIX,
  DEPRECATED_TRENDS_PREFIX,
  PARITY_CATEGORIES,
  PARITY_OPERATIONS,
  REQUIRED_PARITY,
  operationKey,
} from "./parityManifest";

const SRC_ROOT = resolve(__dirname, "..");

describe("API/UI parity contract (Phase 8)", () => {
  it("classifies every inventory entry with a valid category", () => {
    expect(PARITY_OPERATIONS.length).toBeGreaterThan(80);
    const keys = new Set<string>();
    for (const op of PARITY_OPERATIONS) {
      expect(PARITY_CATEGORIES).toContain(op.category);
      const key = operationKey(op);
      expect(keys.has(key)).toBe(false);
      keys.add(key);
    }
  });

  it("requires client+ui for USER_FACING_UI and exemptionReason otherwise", () => {
    for (const op of PARITY_OPERATIONS) {
      if (op.category === "USER_FACING_UI") {
        expect(op.client, operationKey(op)).toBeTruthy();
        expect(op.ui, operationKey(op)).toBeTruthy();
        expect(op.exemptionReason, operationKey(op)).toBeUndefined();
      } else {
        expect(op.exemptionReason?.trim().length, operationKey(op)).toBeGreaterThan(10);
      }
    }
  });

  it("keeps frontend clients and UI owners wired for USER_FACING_UI ops", () => {
    for (const op of PARITY_OPERATIONS) {
      if (op.category !== "USER_FACING_UI" && op.category !== "FRONTEND_INTERNAL") {
        continue;
      }
      if (!op.client) {
        continue;
      }
      const [file, symbol] = op.client.split("#");
      expect(file && symbol, operationKey(op)).toBeTruthy();
      const clientPath = resolve(SRC_ROOT, file!);
      expect(existsSync(clientPath), clientPath).toBe(true);
      const clientSource = readFileSync(clientPath, "utf8");
      expect(clientSource).toContain(symbol!);

      if (op.ui) {
        const uiPath = resolve(SRC_ROOT, op.ui);
        expect(existsSync(uiPath), uiPath).toBe(true);
        const uiSource = readFileSync(uiPath, "utf8");
        expect(uiSource).toContain(symbol!);
      }
    }
  });

  it("lists required MFA, user, brief, content, and candidate owners", () => {
    const paths = REQUIRED_PARITY.map((entry) => operationKey(entry));
    expect(paths).toEqual(
      expect.arrayContaining([
        "POST /api/v1/auth/mfa/enable",
        "POST /api/v1/auth/mfa/verify",
        "POST /api/v1/auth/mfa/disable",
        "GET /api/v1/users/me",
        "POST /api/v1/briefs/{brief_id}/rewrite",
        "POST /api/v1/briefs/{brief_id}/send-telegram",
        "POST /api/v1/content/asset-groups/{asset_group_id}/regenerate",
        "GET /api/v1/stories/candidates/{candidate_id}",
      ]),
    );
  });

  it("documents stories as canonical and trends as deprecated", () => {
    expect(CANONICAL_STORY_PREFIX).toBe("/api/v1/stories");
    expect(DEPRECATED_TRENDS_PREFIX).toBe("/api/v1/trends");
  });
});
