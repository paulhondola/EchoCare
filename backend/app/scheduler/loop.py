"""The scheduler loop: every few seconds, the work nothing else triggers (06 §1, G9).

One copy works at a time, whichever holds a Postgres advisory lock, so a deploy that
runs two API copies for a while does not dial twice.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.campaigns.service import cancel_lapsed
from app.core.db import Session, engine
from app.homenode.service import report_inactivity, silence_home_nodes
from app.medical.service import start_analyses
from app.memory.service import start_summaries
from app.scheduler.dialer import dial_due
from app.scheduler.sweep import sweep
from app.seniors.service import prune_watch_readings, silence_watches

log = logging.getLogger("echocare.scheduler")

# Session-level, unlike CAMPAIGN_LOCK: the steps commit mid-tick, which would end a
# transaction-level lock.
LOCK = 20261024
TICK = 5  # seconds


async def lapse_campaigns(now: datetime) -> None:
    async with Session() as session:
        await cancel_lapsed(session, now)
        await session.commit()


async def silence(now: datetime) -> int:
    async with Session() as session:
        return await silence_watches(session, now)


async def silence_nodes(now: datetime) -> int:
    async with Session() as session:
        return await silence_home_nodes(session, now)


async def node_inactivity(now: datetime) -> int:
    async with Session() as session:
        return await report_inactivity(session, now)


async def prune(now: datetime) -> int:
    async with Session() as session:
        return await prune_watch_readings(session, now)


async def tick(now: datetime | None = None) -> bool:
    """One pass of the steps at `now`; False when another copy holds the lock.

    A step that raises is logged and the others still run.
    """
    now = now or datetime.now(UTC)
    # The lock's own connection, held for the whole tick; the steps open their own.
    async with engine.connect() as conn:
        if not await conn.scalar(select(func.pg_try_advisory_lock(LOCK))):
            return False
        try:
            counts = {}
            for name, step in (
                ("lapsed", lapse_campaigns),
                ("dialed", dial_due),
                ("swept", sweep),
                ("silenced", silence),
                ("nodes silenced", silence_nodes),
                ("nodes inactive", node_inactivity),
                ("pruned", prune),
                ("summarized", start_summaries),
                ("analyzed", start_analyses),
            ):
                try:
                    counts[name] = await step(now)
                except Exception:
                    log.exception("tick: %s failed", name)
            # lapsing returns nothing to count
            done = {k: v for k, v in counts.items() if k != "lapsed"}
            if any(done.values()):
                log.info("tick: %s", ", ".join(f"{k} {v}" for k, v in done.items()))
        finally:
            await conn.scalar(select(func.pg_advisory_unlock(LOCK)))
    return True


async def run() -> None:
    while True:
        try:
            await tick()
        except Exception:
            log.exception("tick failed")
        await asyncio.sleep(TICK)
