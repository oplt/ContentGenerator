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

## Route stability

Page shell remains `ChessVideoPage` at `/dashboard/chess-video` (see
[`chess-frontend-structure.md`](./chess-frontend-structure.md)).
