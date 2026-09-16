/**
 * §24 — source / freshness display helpers.
 *
 * Distinguish game date vs source retrieval vs catalog update.
 * Never imply famous historical games are "fresh" just because a source was re-imported.
 * Do not surface credentials, fingerprints, or raw job payloads.
 */

export type FreshnessGame = {
  is_famous: boolean;
  is_recent?: boolean;
  game_date?: string | null;
  year?: number | null;
  source_provider?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

export type MetaLine = { label: string; value: string };

/** Fresh/stale cues belong on recent/provider-backed surfaces — not famous history. */
export function shouldShowFreshnessCue(game: Pick<FreshnessGame, "is_famous">): boolean {
  return !game.is_famous;
}

export function formatDisplayDateTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function formatDisplayDate(isoOrYear: string | number | null | undefined): string | null {
  if (isoOrYear == null || isoOrYear === "") return null;
  if (typeof isoOrYear === "number") return String(isoOrYear);
  // Prefer date-only when ISO datetime.
  if (/^\d{4}-\d{2}-\d{2}/.test(isoOrYear)) return isoOrYear.slice(0, 10);
  const d = new Date(isoOrYear);
  if (Number.isNaN(d.getTime())) return String(isoOrYear);
  return d.toLocaleDateString();
}

export function gamePlayedDate(game: FreshnessGame): string | null {
  return formatDisplayDate(game.game_date) ?? formatDisplayDate(game.year);
}

export function sourceProviderLabel(provider: string | null | undefined): string | null {
  const p = (provider || "").trim();
  return p || null;
}

/** Compact detail lines — clear labels, no "fresh" for famous re-imports. */
export function buildGameCatalogMeta(game: FreshnessGame): MetaLine[] {
  const lines: MetaLine[] = [];
  const played = gamePlayedDate(game);
  if (played) lines.push({ label: "Game date", value: played });

  const source = sourceProviderLabel(game.source_provider);
  if (source) lines.push({ label: "Source", value: source });

  const catalogUpdated = formatDisplayDateTime(game.updated_at);
  if (catalogUpdated) {
    lines.push({ label: "Catalog updated", value: catalogUpdated });
  }

  return lines;
}

export function dailyFreshnessLabel(opts: {
  is_stale: boolean;
  freshness?: "fresh" | "stale" | string | null;
}): "Fresh" | "Stale" {
  if (opts.is_stale || opts.freshness === "stale") return "Stale";
  return "Fresh";
}

export function analysisEngineSummary(opts: {
  status: string;
  engine_name?: string | null;
  engine_version?: string | null;
  reused?: boolean | null;
}): string {
  const parts = [`Status: ${opts.status}`];
  if (opts.engine_name) {
    parts.push(
      opts.engine_version
        ? `${opts.engine_name} ${opts.engine_version}`
        : opts.engine_name,
    );
  }
  if (opts.reused) parts.push("Cached analysis reused");
  return parts.join(" · ");
}
