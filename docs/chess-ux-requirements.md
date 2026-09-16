# Chess UX requirements (Phase 29)

Chess UI follows the existing SignalForge dashboard patterns — tabs, cards,
filters, dialogs, skeletons, empty/error states, tooltips, and responsive
layouts — and treats game search as a **research / content-selection** surface,
not a database admin console.

## Patterns in use

| Pattern | Where |
|---------|--------|
| Tabs | `ChessVideoPage` (Games / Puzzles / Create / Preview / History); games sub-tabs Search / Famous / Imported |
| Cards | `GameCard`, `PuzzleCard`, filter panels |
| Filters | `GameFilters`, `PuzzleFilters`, imported-source filter |
| Dialogs | `GameDetailsDialog` for compact viewports / **View game** |
| Loading skeletons | `ChessListSkeleton` in search / famous / imported / puzzle browse |
| Empty states | `EmptyState` in panels and detail panes |
| Error states | `ErrorState` with retry on catalog queries |
| Tooltips | `FieldHelp` / `SectionHelp` on search filters and guidance |
| Responsive | Side detail on `xl+`; dialog below `xl` |

## Research / selection feel

- Search copy emphasizes finding matches worth analyzing or turning into video.
- Cards show player title, place · year · round, opening, and **★ Famous**.
- Quick actions on each card: **View game**, **Analyze**, **Create video**.
- Detail pane / dialog keeps move review, Stockfish, provenance, and video handoff.

## Source + freshness (§24)

Users should understand provenance without infrastructure noise.

| Field | Meaning | Where |
|-------|---------|--------|
| Game date | When the game was played | `GameCatalogMeta` |
| Source | Provider / archive name | Card (non-famous), meta, provenance |
| Source retrieved | When we fetched that source | Provenance (`Source retrieved` / `Source recorded` for famous) |
| Catalog updated | When the local row changed | `GameCatalogMeta` |
| Fresh / Stale | Daily puzzle only | `DailyPuzzlePanel` |
| Analysis status + engine/version | Stockfish job outcome | `AnalyzeGameAction` |

**Do not** show credentials, fingerprints, import batch ids, or raw job JSON.
**Do not** put Fresh/Stale on famous historical games just because a source was re-imported.
Helpers: `sourceFreshness.ts`. Analysis reuse surfaces as “Cached analysis reused” (no fingerprint).

## Frontend tests (§31)

Mock SignalForge APIs only. Owning modules listed in
[`chess-frontend-structure.md`](./chess-frontend-structure.md) §31 /
`section31Coverage.test.ts`.

## Admin sync vs browsing (§25)

`CatalogAdminSyncPanel` (Games workspace) queues background jobs for:

* recent-game sync (`provider_sync`)
* daily puzzle (`daily_puzzle_sync`)
* famous enrichment (`enrich_famous`)
* archive import (`pgn_import` + server path)

Requires `content:write`. Browse/search GETs never start synchronization.
Reanalyze remains the per-game Analyze control (fingerprint-aware Stockfish).

## Route stability

Page shell remains `ChessVideoPage` at `/dashboard/chess-video` (see
[`chess-frontend-structure.md`](./chess-frontend-structure.md)).
