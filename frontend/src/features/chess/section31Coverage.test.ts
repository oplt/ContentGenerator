/**
 * §31 — frontend hybrid test coverage map.
 * Scenarios → owning modules. Mock SignalForge only — never Lichess/Chess.com.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const SECTION31_COVERAGE: Record<string, string[]> = {
  local_first_daily_puzzle: ["DailyPuzzlePanel.test.tsx"],
  fresh_stale_display: ["DailyPuzzlePanel.test.tsx", "sourceFreshness.test.ts"],
  recent_game_results: ["GameCard.test.tsx", "GameSearchPanel.test.tsx"],
  historical_famous_distinction: [
    "FamousGamesPanel.test.tsx",
    "GameCard.test.tsx",
    "GameDetails.test.tsx",
  ],
  provider_sync_administration: ["CatalogAdminSyncPanel.test.tsx"],
  analysis_reuse_state: ["AnalyzeGameAction.test.tsx", "sourceFreshness.test.ts"],
  create_video_action: ["CreateVideoAction.test.tsx", "GameCard.test.tsx", "GameDetails.test.tsx"],
};

const FORBIDDEN_IN_TESTS = [
  "api.lichess.org",
  "lichess.org/api",
  "explorer.lichess",
  "api.chess.com",
  "chess.com/api",
];

function walkTestFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...walkTestFiles(full));
      continue;
    }
    if (/\.test\.(ts|tsx)$/.test(name)) out.push(full);
  }
  return out;
}

describe("chess frontend tests (§31)", () => {
  it("maps prompt scenarios onto existing feature tests", () => {
    for (const [area, modules] of Object.entries(SECTION31_COVERAGE)) {
      for (const name of modules) {
        expect(existsSync(path.join(HERE, name)), `${area}:${name}`).toBe(true);
      }
    }
  });

  it("never mocks or calls external chess provider hosts", () => {
    const hits: string[] = [];
    for (const file of walkTestFiles(HERE)) {
      const base = path.basename(file);
      // This file documents forbidden hosts as the deny-list itself.
      if (base === "section31Coverage.test.ts") continue;
      const text = readFileSync(file, "utf8").toLowerCase();
      for (const frag of FORBIDDEN_IN_TESTS) {
        if (text.includes(frag.toLowerCase())) {
          hits.push(`${base}:${frag}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });
});
