/** Phase 28 + §23 — chess frontend structure + SignalForge-only API boundary. */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CHESS_WORKSPACE_TABS } from "./constants";
import {
  ALLOWED_CHESS_API_MODULES,
  FORBIDDEN_CHESS_API_MODULES,
  FORBIDDEN_PROVIDER_HOST_FRAGMENTS,
  UI_CONCEPT_TO_SURFACE,
} from "./frontendSeparation";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(HERE, "../..");

const REQUIRED = [
  "api/chessData.ts",
  "api/chessVideos.ts",
  "features/chess/GameSearchPanel.tsx",
  "features/chess/FamousGamesPanel.tsx",
  "features/chess/PuzzleBrowserPanel.tsx",
  "features/chess/GameFilters.tsx",
  "features/chess/GameCard.tsx",
  "features/chess/GameDetails.tsx",
  "features/chess/MoveViewer.tsx",
  "features/chess/PuzzleCard.tsx",
  "features/chess/PuzzleViewer.tsx",
  "features/chess/CreateVideoAction.tsx",
  "features/chess/ChessListSkeleton.tsx",
  "features/chess/GameDetailsDialog.tsx",
  "features/chess/GamesWorkspace.tsx",
  "features/chess/PuzzlesWorkspace.tsx",
  "features/chess/ContentOpportunityPanel.tsx",
  "features/chess/AnalyzeGameAction.tsx",
  "features/chess/video/CreateVideoTab.tsx",
  "features/chess/DailyPuzzlePanel.tsx",
  "features/chess/CatalogAdminSyncPanel.tsx",
  "features/chess/sourceFreshness.ts",
  "features/chess/frontendSeparation.ts",
  "pages/ChessVideoPage.tsx",
] as const;

function walkTsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      out.push(...walkTsFiles(full));
      continue;
    }
    if (/\.(ts|tsx)$/.test(name)) out.push(full);
  }
  return out;
}

describe("chess frontend structure (Phase 28 / §23)", () => {
  it("keeps suggested feature/api/page files", () => {
    const missing = REQUIRED.filter((rel) => !existsSync(path.join(SRC, rel)));
    expect(missing).toEqual([]);
  });

  it("keeps ChessVideoPage route name (no rename for purity)", () => {
    expect(existsSync(path.join(SRC, "pages/ChessVideoPage.tsx"))).toBe(true);
    expect(existsSync(path.join(SRC, "pages/ChessWorkspacePage.tsx"))).toBe(false);
    expect(CHESS_WORKSPACE_TABS).toEqual([
      "games",
      "puzzles",
      "create",
      "preview",
      "history",
    ]);
  });

  it("does not add forbidden hybrid/provider API modules (§23)", () => {
    const present = FORBIDDEN_CHESS_API_MODULES.filter((rel) =>
      existsSync(path.join(SRC, rel)),
    );
    expect(present).toEqual([]);
    for (const rel of ALLOWED_CHESS_API_MODULES) {
      expect(existsSync(path.join(SRC, rel))).toBe(true);
    }
  });

  it("maps UI concepts onto existing feature surfaces", () => {
    expect(Object.keys(UI_CONCEPT_TO_SURFACE).length).toBeGreaterThanOrEqual(5);
    expect(UI_CONCEPT_TO_SURFACE["Create Video"]).toMatch(/CreateVideo/);
    expect(UI_CONCEPT_TO_SURFACE.Analysis).toMatch(/AnalyzeGame/);
  });

  it("chess API clients only call SignalForge /chess paths", () => {
    for (const rel of ALLOWED_CHESS_API_MODULES) {
      const text = readFileSync(path.join(SRC, rel), "utf8");
      expect(text).toMatch(/apiFetch/);
      expect(text).not.toMatch(/https?:\/\//);
      // Paths are relative to API_BASE (SignalForge), not raw provider hosts.
      const callPaths = [...text.matchAll(/apiFetch<[^>]*>\(\s*[`'"]([^`'"]+)/g)].map(
        (m) => m[1],
      );
      expect(callPaths.length).toBeGreaterThan(0);
      for (const p of callPaths) {
        expect(p.startsWith("/chess")).toBe(true);
      }
    }
  });

  it("features/chess + chess API sources never hardcode provider hosts", () => {
    const roots = [
      path.join(SRC, "api/chessData.ts"),
      path.join(SRC, "api/chessVideos.ts"),
      path.join(SRC, "features/chess"),
    ];
    const files = roots.flatMap((root) =>
      statSync(root).isDirectory() ? walkTsFiles(root) : [root],
    );
    const hits: string[] = [];
    for (const file of files) {
      const base = path.basename(file);
      // Contract/test files may name forbidden hosts as documentation.
      if (base === "frontendSeparation.ts" || base.endsWith(".test.ts")) continue;
      const text = readFileSync(file, "utf8").toLowerCase();
      for (const frag of FORBIDDEN_PROVIDER_HOST_FRAGMENTS) {
        if (text.includes(frag.toLowerCase())) {
          hits.push(`${path.relative(SRC, file)}:${frag}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });
});
