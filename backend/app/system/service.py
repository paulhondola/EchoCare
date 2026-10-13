import time

from sqlalchemy import text

from app.core.db import engine


async def check_database_health() -> float:
    """Executes SELECT 1 on the database and returns latency in milliseconds."""
    t0 = time.perf_counter()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return round((time.perf_counter() - t0) * 1000, 2)
