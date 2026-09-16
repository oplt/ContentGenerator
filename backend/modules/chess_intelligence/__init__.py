"""Chess data and intelligence domain (catalog, providers, analysis).

Render/encode stays in ``chess_video``; this module owns canonical games/puzzles.

Layout (Phase 27): see ``docs/chess-backend-structure.md``.
Celery entrypoints live in ``backend.workers.task_defs.chess_*``, not here.
"""
