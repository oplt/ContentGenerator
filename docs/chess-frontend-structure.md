# Chess frontend structure (Phase 28)

Prompt Phase 28 suggested a minimal feature tree. That layout is **adopted and
extended**. The page file stays `ChessVideoPage.tsx` and the route stays
`/dashboard/chess-video` — renaming to `ChessWorkspacePage` is deferred so
navigation and deep links do not break.

## Finalized layout

```text
frontend/src/api/
├── chessData.ts              # catalog / analysis / provenance / game→video
└── chessVideos.ts            # validate / create / jobs / retry

frontend/src/features/chess/
├── index.ts
├── constants.ts
├── ChessBoardPreview.tsx
├── ChessCatalogWorkspace.tsx
├── GamesWorkspace.tsx
├── PuzzlesWorkspace.tsx
├── GameSearchPanel.tsx
├── FamousGamesPanel.tsx
├── ImportedGamesPanel.tsx
├── CatalogAdminSyncPanel.tsx # §25 privileged job enqueue (not browse)
├── PuzzleBrowserPanel.tsx
├── DailyPuzzlePanel.tsx
├── GameFilters.tsx
├── PuzzleFilters.tsx
├── GameCard.tsx
├── PuzzleCard.tsx
├── GameDetails.tsx
├── GameCatalogMeta.tsx       # §24 game date / source / catalog updated
├── sourceFreshness.ts        # §24 freshness display rules
├── PuzzleViewer.tsx
├── MoveViewer.tsx
├── CreateVideoAction.tsx
├── AnalyzeGameAction.tsx
├── ContentOpportunityPanel.tsx
├── ProvenancePanel.tsx
├── hooks/
│   ├── useChessGames.ts
│   └── useChessPuzzles.ts
└── video/
    ├── CreateVideoTab.tsx
    ├── PreviewVideoTab.tsx
    ├── VideoHistoryTab.tsx
    ├── createParts.tsx
    ├── status.tsx
    └── index.ts

frontend/src/pages/
└── ChessVideoPage.tsx        # workspace shell (games + puzzles + create/preview/history)
```

## §31 — frontend hybrid tests

Update/owning modules (mock SignalForge `chessData` / hooks only — never Lichess):

| Scenario | Tests |
|----------|-------|
| Local-first daily + fresh/stale | `DailyPuzzlePanel.test.tsx`, `sourceFreshness.test.ts` |
| Recent vs famous | `GameCard.test.tsx`, `GameSearchPanel.test.tsx`, `FamousGamesPanel.test.tsx` |
| Admin provider sync | `CatalogAdminSyncPanel.test.tsx` |
| Analysis reuse state | `AnalyzeGameAction.test.tsx` |
| Create Video | `CreateVideoAction.test.tsx` |

Coverage guard: `section31Coverage.test.ts`.

## Suggested → actual

| Phase 28 suggestion | Status |
|---------------------|--------|
| `api/chessData.ts` + `chessVideos.ts` | Present |
| Search / famous / puzzles panels | Present |
| Filters, cards, details, move viewer | Present |
| `PuzzleViewer.tsx` | Present (extracted from puzzles workspace) |
| `CreateVideoAction.tsx` | Present |
| `pages/ChessVideoPage.tsx` | Present; **not** renamed |
| Workspaces, hooks, video tabs, analysis/provenance | Added extensions |

API access stays in `src/api/`. Feature UI stays under `features/chess/`. Page is a thin tab shell.

## §23 — keep this separation

| Keep | Do **not** add |
|------|----------------|
| `api/chessData.ts` | `chessHybrid.ts`, `historicalChessApi.ts` |
| `api/chessVideos.ts` | `lichessApi.ts` / Chess.com clients in frontend |
| `features/chess/*` panels | Provider credentials or direct remote fetches |

Provider access is **backend-only**. Normal UI uses the local SignalForge API.
UI concepts (Famous / Recent / Puzzles / Opportunity / Create / Analysis) map onto
existing panels — inspect UX before changing navigation; do not grow
`ChessVideoPage` into a monolith.

Contract: `features/chess/frontendSeparation.ts` + `structure.test.ts`.

UX patterns (empty/error/skeleton/dialog/tooltips): see [`chess-ux-requirements.md`](./chess-ux-requirements.md).
