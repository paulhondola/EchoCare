"""Campaigns: a DAS press queues one call per active senior (UC-05, 04 §2, Q1-Q4)."""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, literal, select, update
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.service import Caller, refuse
from app.campaigns.models import Campaign
from app.campaigns.schemas import CampaignForm, CampaignProgress, CampaignSummary
from app.incidents.models import UNRESOLVED, Incident
from app.seniors.models import EnrollmentState, Senior
from app.status.engine import Severity
from app.voice.calls import CallState
from app.voice.models import Call, CallTrigger

log = logging.getLogger("echocare.campaigns")

# How long a campaign's warning lasts, in demo mode too (06 §3, Q4).
WARNING = timedelta(hours=24)

# One lock for starting a campaign, so two presses at once make one (Q3). A key of its
# own, distinct from staff.service.STAFF_LOCK.
CAMPAIGN_LOCK = 20261017


def bucket(state: CallState, final_severity: Severity | None) -> str | None:
    """The progress count a senior's latest attempt falls under, if any (design 4.1)."""
    if state == CallState.queued:
        return "waiting"
    if state == CallState.canceled:
        return "canceled"
    return final_severity.name if isinstance(final_severity, Severity) else None


async def progress_of(
    session: AsyncSession, campaign_ids: list[uuid.UUID]
) -> dict[uuid.UUID, CampaignProgress]:
    """Per campaign, each senior counted once, by their latest attempt in it."""
    latest = await session.execute(
        select(Call.campaign_id, Call.state, Call.final_severity)
        .where(Call.campaign_id.in_(campaign_ids))
        .ext(distinct_on(Call.campaign_id, Call.senior_id))
        .order_by(
            Call.campaign_id,
            Call.senior_id,
            Call.attempt.desc(),
            Call.created_at.desc(),
        )
    )
    counts: dict[uuid.UUID, Counter[str]] = {id: Counter() for id in campaign_ids}
    for campaign_id, state, final_severity in latest:
        counts[campaign_id]["total"] += 1
        if (name := bucket(state, final_severity)) is not None:
            counts[campaign_id][name] += 1
    return {
        id: CampaignProgress(**{f: c[f] for f in CampaignProgress.model_fields})
        for id, c in counts.items()
    }


async def campaign_summaries(
    session: AsyncSession, campaign_id: uuid.UUID | None = None
) -> list[CampaignSummary]:
    """Campaigns, newest first (04 §1); only `campaign_id` if given."""
    query = (
        select(Campaign, User.display_name)
        .join(User, User.id == Campaign.started_by)
        .order_by(Campaign.started_at.desc(), Campaign.id)
    )
    if campaign_id is not None:
        query = query.where(Campaign.id == campaign_id)
    rows = (await session.execute(query)).all()
    progress = await progress_of(session, [c.id for c, _ in rows])
    now = datetime.now(UTC)
    return [
        CampaignSummary(
            id=c.id,
            kind=c.kind,
            level=c.level,
            started_by_name=name,
            started_at=c.started_at,
            warning_until=c.warning_until,
            active=c.warning_until > now,
            progress=progress[c.id],
        )
        for c, name in rows
    ]


async def start_campaign(
    session: AsyncSession, caller: Caller, form: CampaignForm
) -> tuple[CampaignSummary, bool]:
    """Starts a campaign and queues its calls, or answers the running one (Q3).

    The bool is "created". A running campaign of the same kind and level, one whose
    warning has not lapsed, is answered and nothing changes. Otherwise one call is queued
    for each `active` senior with no unresolved incident; a senior who already has a live
    call is skipped by `uq_calls_live_senior` (05 §3), so no one gets two.
    """
    await session.execute(select(func.pg_advisory_xact_lock(CAMPAIGN_LOCK)))
    now = datetime.now(UTC)
    # One clock for the whole start: a warning that lapses between two reads would be
    # canceled here and still counted as running below. Frees the seniors of a lapsed
    # campaign for this one.
    await cancel_lapsed(session, now)
    running = await session.scalar(
        select(Campaign.id).where(
            Campaign.kind == form.kind,
            Campaign.level == form.level,
            Campaign.warning_until > now,
        )
    )
    if running is not None:
        await session.commit()  # releases the lock and keeps cancel_lapsed's work
        return (await campaign_summaries(session, running))[0], False

    campaign = Campaign(
        kind=form.kind,
        level=form.level,
        started_by=caller.user.id,
        started_at=now,
        warning_until=now + WARNING,
    )
    session.add(campaign)
    await session.flush()  # the database makes the id
    await session.execute(
        insert(Call)
        .from_select(
            [
                Call.senior_id,
                Call.trigger,
                Call.campaign_id,
                Call.attempt,
                Call.starting_severity,
                Call.state,
                Call.due_at,
            ],
            select(
                Senior.id,
                literal(CallTrigger.campaign, Call.trigger.type),
                literal(campaign.id, Call.campaign_id.type),
                literal(1, Call.attempt.type),
                literal(Severity.green, Call.starting_severity.type),
                literal(CallState.queued, Call.state.type),
                literal(now, Call.due_at.type),
            ).where(
                Senior.enrollment_state == EnrollmentState.active,
                ~select(Incident.id)
                .where(Incident.senior_id == Senior.id, Incident.status.in_(UNRESOLVED))
                .exists(),
            ),
        )
        .on_conflict_do_nothing()
    )
    await session.commit()
    return (await campaign_summaries(session, campaign.id))[0], True


async def cancel_lapsed(session: AsyncSession, now: datetime | None = None) -> None:
    """Cancels the queued calls of every campaign whose warning has lapsed (design 4.1).

    There is no scheduler, so the campaign endpoints do this lazily, first. `now` is the
    caller's clock when it reads the warnings too. Does not commit: the caller's
    transaction does.
    """
    now = now or datetime.now(UTC)
    await session.execute(
        update(Call)
        .where(
            Call.state == CallState.queued,
            Call.campaign_id.in_(
                select(Campaign.id).where(Campaign.warning_until <= now)
            ),
        )
        .values(state=CallState.canceled, ended_at=now)
    )


async def end_campaign(
    session: AsyncSession, campaign_id: uuid.UUID
) -> CampaignSummary:
    """Ends a campaign's warning now and cancels its queued calls, redials included (Q9).

    `warning_until` becomes the earlier of itself and now, so a lapsed warning keeps its
    end and a repeat changes nothing. Codes are untouched. Commits.
    """
    await session.execute(select(func.pg_advisory_xact_lock(CAMPAIGN_LOCK)))
    now = datetime.now(UTC)
    ended = await session.scalar(
        update(Campaign)
        .where(Campaign.id == campaign_id)
        .values(warning_until=func.least(Campaign.warning_until, now))
        .returning(Campaign.id)
    )
    if ended is None:
        log.info("refused not_found: campaign %s", campaign_id)
        raise refuse(404, "not_found")
    await session.execute(
        update(Call)
        .where(Call.campaign_id == campaign_id, Call.state == CallState.queued)
        .values(state=CallState.canceled, ended_at=now)
    )
    await session.commit()
    return (await campaign_summaries(session, campaign_id))[0]


async def warning_active(session: AsyncSession) -> bool:
    """True while any campaign's warning has not lapsed: `/profile`'s flag (Q5)."""
    return bool(
        await session.scalar(
            select(exists().where(Campaign.warning_until > datetime.now(UTC)))
        )
    )
