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
├── PuzzleBrowserPanel.tsx
├── DailyPuzzlePanel.tsx
├── GameFilters.tsx
├── PuzzleFilters.tsx
├── GameCard.tsx
├── PuzzleCard.tsx
├── GameDetails.tsx
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

UX patterns (empty/error/skeleton/dialog/tooltips): see [`chess-ux-requirements.md`](./chess-ux-requirements.md).
