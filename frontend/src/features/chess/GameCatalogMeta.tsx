import type { ChessGame } from "../../api/chessData";
import {
  buildGameCatalogMeta,
  shouldShowFreshnessCue,
  sourceProviderLabel,
} from "./sourceFreshness";

export type GameCatalogMetaProps = {
  game: ChessGame;
};

/** §24 — game date / source / catalog update (not a freshness badge for famous). */
export function GameCatalogMeta({ game }: GameCatalogMetaProps) {
  const lines = buildGameCatalogMeta(game);
  if (lines.length === 0) return null;

  return (
    <ul className="space-y-0.5 text-xs text-muted-foreground" aria-label="Catalog metadata">
      {lines.map((line) => (
        <li key={line.label} className="flex flex-wrap gap-x-2">
          <span className="font-medium text-foreground/80">{line.label}</span>
          <span>{line.value}</span>
        </li>
      ))}
      {shouldShowFreshnessCue(game) && game.is_recent ? (
        <li className="text-muted-foreground">Recently discovered in catalog</li>
      ) : null}
      {!shouldShowFreshnessCue(game) && sourceProviderLabel(game.source_provider) ? (
        <li className="text-muted-foreground">
          Famous catalog entry — source retrieval is provenance, not freshness
        </li>
      ) : null}
    </ul>
  );
}
