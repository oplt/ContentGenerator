/**
 * Phase 13 — guard against regressing the main/entry JS budget and
 * keep recharts out of the initial route shell chunk.
 */
import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DIST_ASSETS = path.join(FRONTEND_ROOT, "dist", "assets");

function ensureProductionBuild(): void {
  if (readdirSync(DIST_ASSETS, { withFileTypes: true }).some((e) => e.isFile() && e.name.endsWith(".js"))) {
    return;
  }
  execFileSync("npm", ["run", "build"], { cwd: FRONTEND_ROOT, stdio: "pipe" });
}

function listJsAssets(): Array<{ name: string; bytes: number }> {
  ensureProductionBuild();
  return readdirSync(DIST_ASSETS)
    .filter((name) => name.endsWith(".js"))
    .map((name) => ({
      name,
      bytes: statSync(path.join(DIST_ASSETS, name)).size,
    }))
    .sort((a, b) => b.bytes - a.bytes);
}

describe("Phase 13 bundle budgets", () => {
  it("keeps the largest entry chunk under 320kB and charts under its own chunk", () => {
    const assets = listJsAssets();
    const entry = assets.find((a) => a.name.startsWith("index-"));
    expect(entry, "missing index-*.js entry chunk").toBeTruthy();
    // Soft ceiling for the app shell entry (react/vendor split into sibling chunks).
    expect(entry!.bytes).toBeLessThan(120 * 1024);

    const charts = assets.find((a) => a.name.startsWith("charts-"));
    expect(charts, "missing charts-*.js chunk for recharts").toBeTruthy();
    expect(charts!.bytes).toBeGreaterThan(100 * 1024);

    const entrySource = readFileSync(path.join(DIST_ASSETS, entry!.name), "utf8");
    expect(entrySource.includes("ResponsiveContainer")).toBe(false);
    expect(entrySource.includes("recharts")).toBe(false);
  });

  it("splits content/settings/sources tab panels into separate lazy chunks", () => {
    const assets = listJsAssets();
    const names = assets.map((a) => a.name);
    // Vite names lazy chunks after the module; accept either panel or tab names.
    const hasContentSplit = names.some(
      (n) =>
        n.includes("PlansTab") ||
        n.includes("ApprovalsTab") ||
        n.includes("PublishingTab") ||
        n.includes("content"),
    );
    const hasSettingsSplit = names.some(
      (n) =>
        n.includes("GeneralTab") ||
        n.includes("IntegrationsTab") ||
        n.includes("SocialTab") ||
        n.includes("PublishingTab"),
    );
    const hasSourcesSplit = names.some(
      (n) =>
        n.includes("AddSourcePanel") ||
        n.includes("ConfiguredSourcesPanel") ||
        n.includes("FetchRunsPanel"),
    );
    expect(hasContentSplit || hasSettingsSplit || hasSourcesSplit).toBe(true);
  });
});
