import {
  analysisEngineSummary,
  buildGameCatalogMeta,
  dailyFreshnessLabel,
  shouldShowFreshnessCue,
} from "./sourceFreshness";

describe("sourceFreshness (§24)", () => {
  it("does not show freshness cues for famous games", () => {
    expect(shouldShowFreshnessCue({ is_famous: true })).toBe(false);
    expect(shouldShowFreshnessCue({ is_famous: false })).toBe(true);
  });

  it("labels game date, source, and catalog update distinctly", () => {
    const lines = buildGameCatalogMeta({
      is_famous: false,
      game_date: "2024-03-01T12:00:00Z",
      source_provider: "lichess_masters",
      updated_at: "2026-09-16T10:00:00Z",
    });
    expect(lines.map((l) => l.label)).toEqual([
      "Game date",
      "Source",
      "Catalog updated",
    ]);
    expect(lines[0]?.value).toBe("2024-03-01");
    expect(lines[1]?.value).toBe("lichess_masters");
  });

  it("still lists catalog dates for famous games without calling them fresh", () => {
    const lines = buildGameCatalogMeta({
      is_famous: true,
      year: 1972,
      source_provider: "pgn_archive",
      updated_at: "2026-09-16T10:00:00Z",
    });
    expect(lines.some((l) => l.label === "Game date")).toBe(true);
    expect(lines.some((l) => /fresh/i.test(l.label))).toBe(false);
  });

  it("maps daily puzzle freshness labels", () => {
    expect(dailyFreshnessLabel({ is_stale: false, freshness: "fresh" })).toBe("Fresh");
    expect(dailyFreshnessLabel({ is_stale: true, freshness: "stale" })).toBe("Stale");
  });

  it("summarizes analysis status with engine version, not fingerprints", () => {
    expect(
      analysisEngineSummary({
        status: "completed",
        engine_name: "Stockfish",
        engine_version: "16",
      }),
    ).toBe("Status: completed · Stockfish 16");
  });

  it("surfaces analysis reuse without fingerprints", () => {
    expect(
      analysisEngineSummary({
        status: "completed",
        engine_name: "Stockfish",
        engine_version: "16",
        reused: true,
      }),
    ).toBe("Status: completed · Stockfish 16 · Cached analysis reused");
  });
});
