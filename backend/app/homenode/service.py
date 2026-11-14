import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import get_settings
from app.homenode.models import HomeNodeState, NodeCondition, RoomState
from app.homenode.schemas import RoomReadingForm, RoomReadingView
from app.incidents.models import EventType
from app.incidents.service import intake_event

log = logging.getLogger("echocare.homenode")

# The room limits (06 §3). Orientative, no medical value; README open question 11.
COLD_BELOW = 16.0
HEAT_ABOVE = 30.0
# A temperature outside this is a sensor fault, used for nothing (04 §3).
PLAUSIBLE = (-10.0, 50.0)


def hold_time() -> timedelta:
    """How long the room stays out of range before a call (P21, 06 §3)."""
    return timedelta(seconds=30) if get_settings().demo_mode else timedelta(minutes=30)


def out_of_range(celsius: float) -> RoomState | None:
    if celsius < COLD_BELOW:
        return RoomState.cold
    if celsius > HEAT_ABOVE:
        return RoomState.hot
    return None


def room_state(celsius: float, forecast_60m: float | None) -> RoomState:
    """What the node shows (P26): the room past a limit, or about to be by the node's
    own forecast. A forecast only warns the senior; it never starts a call."""
    now_side = out_of_range(celsius)
    if now_side is not None:
        return now_side
    if forecast_60m is not None:
        soon = out_of_range(forecast_60m)
        if soon is RoomState.cold:
            return RoomState.cold_soon
        if soon is RoomState.hot:
            return RoomState.hot_soon
    return RoomState.ok


def plausible(celsius: float) -> bool:
    return PLAUSIBLE[0] <= celsius <= PLAUSIBLE[1]


async def record_room_reading(
    session: AsyncSession, senior_id: uuid.UUID, form: RoomReadingForm, now: datetime
) -> RoomReadingView:
    """Keeps the node's latest reading and applies the room rule (UC-16, P21): a room
    out of range for the hold time records one `room_cold` or `room_heat` event per
    stretch, which queues a yellow call under the usual intake rules. A reading measured
    before the stored one changes nothing, since the phone may relay late; a time ahead
    of `now` is stored as `now`. Answers with the room state (P26)."""
    measured_at = min(form.measured_at, now)
    if not plausible(form.temperature):
        log.warning(
            "implausible room reading %.1f°C for senior %s", form.temperature, senior_id
        )
        node = await session.get(HomeNodeState, senior_id)
        state = (
            room_state(node.temperature_c, node.forecast_60m_c)
            if node is not None
            else RoomState.ok
        )
        return RoomReadingView(room_state=state, queued=False, call_id=None)

    # The first reading makes the row; every reading then works on it under a lock, so
    # two readings at once cannot both send the stretch's event.
    await session.execute(
        insert(HomeNodeState)
        .values(
            senior_id=senior_id,
            state=NodeCondition.ok,
            last_reading_at=measured_at,
            temperature_c=form.temperature,
        )
        .on_conflict_do_nothing()
    )
    node = await session.scalar(
        select(HomeNodeState)
        .where(HomeNodeState.senior_id == senior_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert node is not None

    if measured_at < node.last_reading_at:
        state = room_state(node.temperature_c, node.forecast_60m_c)
        await session.commit()
        return RoomReadingView(room_state=state, queued=False, call_id=None)

    side = out_of_range(form.temperature)
    if side is None:
        node.out_of_range_since = None
        node.out_of_range_event_sent = False
    elif node.out_of_range_since is None or side != out_of_range(node.temperature_c):
        # A new stretch, or the room went from one side straight to the other
        node.out_of_range_since = measured_at
        node.out_of_range_event_sent = False

    node.state = NodeCondition.ok
    node.last_reading_at = measured_at
    node.temperature_c = form.temperature
    node.humidity_pct = form.humidity
    node.last_motion_at = form.last_motion_at
    node.forecast_60m_c = form.forecast_60m

    queued, call_id = False, None
    if (
        side is not None
        and node.out_of_range_since is not None
        and not node.out_of_range_event_sent
        and measured_at - node.out_of_range_since >= hold_time()
    ):
        event = await intake_event(
            session,
            senior_id,
            # FastAPI's own id: the event is derived here, not sent by a device (04 §0)
            event_id=uuid.uuid7(),
            event_type=EventType.room_cold
            if side is RoomState.cold
            else EventType.room_heat,
            measured_at=measured_at,
            source="home_node",
            snapshot={
                "temperature": form.temperature,
                "humidity": form.humidity,
                "out_of_range_since": node.out_of_range_since.isoformat(),
            },
            now=now,
        )
        node.out_of_range_event_sent = True
        queued, call_id = event.queued, event.call_id

    state = room_state(form.temperature, form.forecast_60m)
    await session.commit()
    return RoomReadingView(room_state=state, queued=queued, call_id=call_id)


async def erase_home_node(session: AsyncSession, senior_id: uuid.UUID) -> None:
    """The senior's room reading, for erasure (GDPR Art. 17). Doesn't commit (ADR-005)."""
    await session.execute(
        delete(HomeNodeState).where(HomeNodeState.senior_id == senior_id)
    )
