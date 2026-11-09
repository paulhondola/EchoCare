"""Which answered calls get a summary, and the task that writes it (design §4).

The scheduler step only starts the work. Each summary runs in its own asyncio task,
outside the locked tick, so the advisory lock never waits on the model.
"""

import asyncio
import logging
import uuid
from collections import Counter
from datetime import datetime, timedelta

from pydantic_ai.models import Model
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.campaigns.models import Campaign
from app.core.db import Session
from app.core.llm import deepinfra_model
from app.core.settings import get_settings
from app.memory.writer import CallFacts, SummaryInput, prompt, summary_agent
from app.seniors.models import EnrollmentState, Senior, SummaryVersion
from app.seniors.service import add_summary, latest_summary, read_content
from app.status.engine import BUCHAREST
from app.voice.calls import CallState
from app.voice.models import Answer, Call, CallTrigger, CallTurn

log = logging.getLogger("echocare.memory")

WELLBEING = {CallTrigger.campaign, CallTrigger.watch, CallTrigger.manual}
ANSWERED = {CallState.completed, CallState.handed_over, CallState.dropped}
WINDOW = timedelta(hours=24)
# A handed-over call's DAS talk keeps arriving as turns after `ended_at` (design §4).
TALK_QUIET = timedelta(minutes=2)
ATTEMPTS = 3
EARLIER = 5

# Per process: a restart forgets them (design §4, "at most 3 times per process").
_running: dict[uuid.UUID, asyncio.Task] = {}  # by senior
_failures: Counter[uuid.UUID] = Counter()  # by call


async def due_calls(session, now: datetime) -> list[uuid.UUID]:
    """At most one call per senior, the oldest that qualifies (design §4)."""
    last = aliased(Call)
    latest_ended = (
        select(last.ended_at)
        .join(SummaryVersion, SummaryVersion.call_id == last.id)
        .where(SummaryVersion.senior_id == Call.senior_id)
        .order_by(SummaryVersion.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    talking = exists().where(
        CallTurn.call_id == Call.id, CallTurn.at >= now - TALK_QUIET
    )
    rows = await session.execute(
        select(Call.id, Call.senior_id)
        .join(Senior, Senior.id == Call.senior_id)
        .where(
            Call.trigger.in_(WELLBEING),
            Call.state.in_(ANSWERED),
            Senior.enrollment_state == EnrollmentState.active,
            Call.ended_at >= now - WINDOW,
            ~exists().where(SummaryVersion.call_id == Call.id),
            (latest_ended.is_(None)) | (Call.ended_at > latest_ended),
            (Call.state != CallState.handed_over) | ~talking,
        )
        .order_by(Call.ended_at, Call.id)
    )
    chosen: dict[uuid.UUID, uuid.UUID] = {}
    for call_id, senior_id in rows:
        if _failures[call_id] < ATTEMPTS and senior_id not in _running:
            chosen.setdefault(senior_id, call_id)
    return list(chosen.values())


def _facts(call: Call, kind, turns, answers) -> CallFacts:
    return CallFacts(
        id=call.id,
        trigger=call.trigger.value,
        campaign_kind=kind.value if kind else None,
        date=(call.ended_at or call.started_at).astimezone(BUCHAREST).date(),
        state=call.state.value,
        final_severity=call.final_severity.name if call.final_severity else None,
        final_certainty=call.final_certainty.name if call.final_certainty else None,
        reason=call.reason,
        turns=turns,
        answers=answers,
    )


async def summary_input(
    session, call_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID | None, SummaryInput]:
    """(senior id, previous version id, what the agent is given) (design §4)."""
    call = await session.get(Call, call_id)
    latest = await latest_summary(session, call.senior_id)
    ended = call.ended_at or call.started_at
    earlier_calls = (
        await session.execute(
            select(Call, Campaign.kind)
            .outerjoin(Campaign, Campaign.id == Call.campaign_id)
            .where(
                Call.senior_id == call.senior_id,
                Call.trigger.in_(WELLBEING),
                Call.state.in_(ANSWERED),
                Call.ended_at < ended,
            )
            .order_by(Call.ended_at.desc())
            .limit(EARLIER)
        )
    ).all()
    kind = await session.scalar(
        select(Campaign.kind).where(Campaign.id == call.campaign_id)
    )
    ids = [call.id, *(c.id for c, _ in earlier_calls)]
    answers: dict[uuid.UUID, list[tuple[str, str, bool, str]]] = {i: [] for i in ids}
    for a in await session.scalars(
        select(Answer).where(Answer.call_id.in_(ids)).order_by(Answer.at)
    ):
        answers[a.call_id].append((a.field.value, a.value, a.clear, a.quote))
    turns = [
        (t.speaker.value, t.content)
        for t in await session.scalars(
            select(CallTurn)
            .where(CallTurn.call_id == call.id)
            .order_by(CallTurn.position)
        )
    ]
    data = SummaryInput(
        previous=read_content(latest) if latest else None,
        call=_facts(call, kind, turns, answers[call.id]),
        earlier=[_facts(c, k, [], answers[c.id]) for c, k in earlier_calls],
    )
    return call.senior_id, latest.id if latest else None, data


async def write_summary(call_id: uuid.UUID, *, model: Model | None = None) -> None:
    """Read, run the agent, store the version. Owns its sessions (design §4)."""
    if model is None:
        settings = get_settings()
        model = deepinfra_model(settings.deepinfra_api_key, settings.summary_model)
    async with Session() as session:
        senior_id, previous_id, data = await summary_input(session, call_id)
    # No session is held while the model works.
    content = (await summary_agent(model).run(prompt(data), deps=data)).output
    async with Session() as session:
        add_summary(
            session,
            senior_id=senior_id,
            call_id=call_id,
            previous_id=previous_id,
            content=content,
            model=model.model_name,
        )
        try:
            await session.commit()
        except IntegrityError:
            # Another API copy wrote this call first (design §4).
            await session.rollback()
            log.info("summary exists, call %s", call_id)
            return
    log.info("summary written, call %s", call_id)


def _finished(senior_id: uuid.UUID, call_id: uuid.UUID, task: asyncio.Task) -> None:
    _running.pop(senior_id, None)
    if task.cancelled():
        return
    if e := task.exception():
        _failures[call_id] += 1
        log.error("summary failed, call %s: %s", call_id, type(e).__name__)


async def start_summaries(now: datetime) -> int:
    """The scheduler step: start one task per due call and return; never awaits one."""
    if not get_settings().deepinfra_api_key:  # no key, no summaries (design §4, R6)
        return 0
    async with Session() as session:
        due = await due_calls(session, now)
        seniors = dict(
            (
                await session.execute(
                    select(Call.id, Call.senior_id).where(Call.id.in_(due))
                )
            ).all()
        )
    for call_id in due:
        senior_id = seniors[call_id]
        task = asyncio.create_task(write_summary(call_id))
        _running[senior_id] = task
        task.add_done_callback(lambda t, s=senior_id, c=call_id: _finished(s, c, t))
    return len(due)
