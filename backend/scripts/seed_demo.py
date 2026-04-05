from __future__ import annotations

import asyncio

from backend.core.bootstrap import bootstrap_application
from backend.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as db:
        await bootstrap_application(db)


if __name__ == "__main__":
    asyncio.run(main())
