import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  CANONICAL_STORY_PREFIX,
  DEPRECATED_TRENDS_PREFIX,
  REQUIRED_PARITY,
} from "../api/parityManifest";

describe("API/UI parity contract (T5.1)", () => {
  it("lists required MFA, user, brief, content, and candidate owners", () => {
    const paths = REQUIRED_PARITY.map((entry) => `${entry.method} ${entry.path}`);
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
      ])
    );
    for (const entry of REQUIRED_PARITY) {
      expect(entry.client).toBeTruthy();
      expect(entry.ui).toBeTruthy();
      expect(entry.owner).not.toBe("ui_exempt");
    }
  });

  it("keeps frontend clients wired for required parity endpoints", () => {
    const root = resolve(__dirname, "..");
    for (const entry of REQUIRED_PARITY) {
      const [file] = (entry.client ?? "").split("#");
      const source = readFileSync(resolve(root, file), "utf8");
      const symbol = (entry.client ?? "").split("#")[1];
      expect(source).toContain(symbol);
      const uiSource = readFileSync(resolve(root, entry.ui!), "utf8");
      expect(uiSource.length).toBeGreaterThan(0);
    }
  });

  it("documents stories as canonical and trends as deprecated", () => {
    expect(CANONICAL_STORY_PREFIX).toBe("/api/v1/stories");
    expect(DEPRECATED_TRENDS_PREFIX).toBe("/api/v1/trends");
  });
});
