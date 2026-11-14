import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import (
    ColumnElement,
    Integer,
    Select,
    and_,
    delete,
    false,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, Role, User
from app.auth.service import (
    Caller,
    add_caregiver_grant,
    edit_caregiver_grant,
    refuse,
    revoke_caregiver_grant,
    sync_senior_grant,
)
from app.codes.models import SeniorStatus
from app.core.changes import Change, ChangeKind, note
from app.core.settings import get_settings
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Senior,
    SummaryVersion,
    WatchCondition,
    WatchReading,
    WatchState,
)
from app.seniors.schemas import (
    CaregiverEditForm,
    CaregiverForm,
    CaregiverView,
    CheckInForm,
    MedicView,
    SeniorForm,
    SeniorSummary,
    SeniorView,
    SignatureForm,
    SummaryContent,
    SummaryVersionView,
    WatchReadingView,
    WatchView,
)

log = logging.getLogger("echocare.seniors")

# What a move does in its own transaction besides the move: the router passes it in,
# since `seniors` can't import `calls` (design §7).
Hook = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]


def reach(caller: Caller, role: Role | None = None) -> ColumnElement[bool]:
    """The seniors this caller reaches, as a condition on `seniors` (auth-layer §3.6).

    A medic their own seniors while they hold the grant, caregivers and the senior
    through grants naming them, DAS every senior past `draft`. The union, as AL2 says.

    `role` narrows it to what that one role reaches, for a home that shows one role
    (seniors SE6). It grants nothing: a role the caller does not hold reaches nobody.
    """
    held = caller.roles if role is None else caller.roles & {role}
    reaches = []
    if Role.medic in held:
        reaches.append(Senior.medic_id == caller.user.id)
    granted = [
        g.senior_id for g in caller.grants if g.role in held and g.senior_id is not None
    ]
    if granted:
        reaches.append(Senior.id.in_(granted))
    if Role.das in held:
        reaches.append(Senior.enrollment_state != EnrollmentState.draft)
    return or_(*reaches) if reaches else false()


def seniors_query(caller: Caller, role: Role | None = None) -> Select:
    return (
        select(Senior).where(reach(caller, role)).order_by(Senior.full_name, Senior.id)
    )


async def senior_summaries(
    session: AsyncSession, caller: Caller, role: Role | None
) -> list[SeniorSummary]:
    """The rows of GET /seniors with each one's current code (Q17). Joined only while
    the senior is `active`: a withdrawn senior's old code must not read as watched."""
    query = (
        seniors_query(caller, role)
        .add_columns(
            SeniorStatus.code,
            SeniorStatus.reason,
            SeniorStatus.since,
            WatchState.state,
        )
        .outerjoin(WatchState, WatchState.senior_id == Senior.id)
        .outerjoin(
            SeniorStatus,
            and_(
                SeniorStatus.senior_id == Senior.id,
                Senior.enrollment_state == EnrollmentState.active,
            ),
        )
    )
    fields = SeniorSummary.model_fields.keys() - {
        "code",
        "reason",
        "since",
        "watch_state",
        "medical_record_state",
    }
    return [
        SeniorSummary(
            **{name: getattr(senior, name) for name in fields},
            code=code,
            reason=reason,
            since=since,
            watch_state=watch
            if sees_watch(caller, senior.id, senior.medic_id)
            else None,
        )
        for senior, code, reason, since, watch in await session.execute(query)
    ]


async def reach_senior(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *,
    lock: bool = False,
    full: bool = False,
) -> Senior:
    """The senior, if the caller reaches them; otherwise 404 `not_found` (AL8).

    `lock` is FOR NO KEY UPDATE, not FOR UPDATE: inserting a grant, a call or an
    incident takes FOR KEY SHARE on the senior's row through its foreign key, which a
    plain FOR UPDATE would block (seniors §6.2). `full` is that FOR UPDATE, for an
    erasure, taken in one step: upgrading from NO KEY UPDATE deadlocks with a writer
    holding KEY SHARE that then updates the senior (design 2026-11-14).
    """
    query = select(Senior).where(Senior.id == senior_id, reach(caller))
    if lock or full:
        query = query.with_for_update(key_share=not full)
    senior = await session.scalar(query)
    if senior is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    return senior


async def own_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> Senior:
    """A senior the caller registered, for the medic's commands (04 §2).

    Out of reach is 404; within reach but someone else's, such as DAS looking at a
    submitted senior, is 403 `not_allowed`. The row stays locked until the request
    ends, so the medic's commands on one senior run one at a time: submit's check
    cannot interleave with an edit or a caregiver's removal.
    """
    senior = await reach_senior(session, caller, senior_id, lock=True)
    if Role.medic not in caller.roles or senior.medic_id != caller.user.id:
        log.info("refused not_allowed: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(403, "not_allowed")
    return senior


async def editable_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, *, full: bool = False
) -> Senior:
    """A senior the caller may edit: the registering medic, or DAS within reach (SE9).

    Locked like `own_senior`, so edits and caregiver changes on one senior run one at
    a time; `full` as in `reach_senior`. Out of reach is 404; reached but neither the
    registering medic nor DAS past `draft` is 403 `not_allowed`.
    """
    senior = await reach_senior(session, caller, senior_id, lock=True, full=full)
    registering_medic = Role.medic in caller.roles and senior.medic_id == caller.user.id
    # SE9: DAS edits what she reaches as DAS, past draft; a caregiver grant is not that
    reaches_as_das = (
        Role.das in caller.roles and senior.enrollment_state != EnrollmentState.draft
    )
    if not registering_medic and not reaches_as_das:
        log.info("refused not_allowed: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(403, "not_allowed")
    return senior


def caregivers_query(senior_id: uuid.UUID) -> Select:
    return (
        select(
            User.id.label("user_id"),
            User.display_name,
            User.phone_e164,
            Grant.relation,
        )
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior_id, Grant.role == Role.caregiver)
        .order_by(User.display_name, User.id)
    )


async def consent_fields(session: AsyncSession, senior_id: uuid.UUID) -> dict[str, Any]:
    """`consent`, `consent_given_at` and `signed_at` for GET /seniors/{id} (04 §1, G7).
    One read of her few consent rows, newest first, without the signature strokes."""
    rows = (
        await session.execute(
            select(Consent.decision, Consent.method, Consent.at)
            .where(Consent.senior_id == senior_id)
            .order_by(Consent.at.desc(), Consent.id.desc())
        )
    ).all()
    signature = ConsentMethod.signature
    decided = next((r for r in rows if r.method != signature), None)
    given = next(
        (
            r
            for r in rows
            if r.decision == ConsentDecision.given
            and r.method in (ConsentMethod.call, ConsentMethod.app)
        ),
        None,
    )
    signed = next((r for r in rows if r.method == signature), None)
    return {
        "consent": decided
        and {"decision": decided.decision, "method": decided.method, "at": decided.at},
        "consent_given_at": given and given.at,
        "signed_at": signed and signed.at,
    }


async def senior_view(session: AsyncSession, senior: Senior) -> SeniorView:
    medic = await session.get(User, senior.medic_id)
    caregivers = (await session.execute(caregivers_query(senior.id))).mappings()
    status = {}
    if senior.enrollment_state == EnrollmentState.active and (
        row := await session.get(SeniorStatus, senior.id)
    ):
        status = {"code": row.code, "reason": row.reason, "since": row.since}
    fields = SeniorView.model_fields.keys() - {
        "medic",
        "caregivers",
        "code",
        "reason",
        "since",
        "call_in_progress",
        "watch_state",
        "last_pulse",
        "app_signed_in",
        "consent",
        "consent_given_at",
        "signed_at",
    }
    return SeniorView(
        **{name: getattr(senior, name) for name in fields},
        **await consent_fields(session, senior.id),
        **status,
        medic=MedicView.model_validate(medic, from_attributes=True),
        caregivers=[CaregiverView.model_validate(dict(c)) for c in caregivers],
    )


async def forms_of_address(
    session: AsyncSession, senior_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """For GET /me's grants (auth-layer §3.3)."""
    if not senior_ids:
        return {}
    rows = await session.execute(
        select(Senior.id, Senior.form_of_address).where(Senior.id.in_(senior_ids))
    )
    return dict(rows.all())


REQUIRED_TO_SUBMIT = ("street", "street_number")


def missing_address(registration: Senior | SeniorForm) -> list[str]:
    return [name for name in REQUIRED_TO_SUBMIT if not getattr(registration, name)]


async def has_caregiver(session: AsyncSession, senior_id: uuid.UUID) -> bool:
    return await session.scalar(
        select(
            select(Grant.id)
            .where(Grant.senior_id == senior_id, Grant.role == Role.caregiver)
            .exists()
        )
    )


async def missing_to_submit(session: AsyncSession, senior: Senior) -> list[str]:
    missing = missing_address(senior)
    if not await has_caregiver(session, senior.id):
        missing.append("caregiver")
    return missing


async def move(
    session: AsyncSession,
    caller: Caller,
    senior: Senior,
    before: EnrollmentState | tuple[EnrollmentState, ...],
    after: EnrollmentState,
    *,
    values: dict[str, Any] | None = None,
) -> None:
    """`before` (any of them, if a tuple) -> `after`, only where the senior is still
    there, so of two at once one wins (05 §3's pattern). `values` are more columns set
    in the same statement. Already `after` is `already_done`, anything else
    `wrong_state`; either way nothing changes (04 §0)."""
    states = before if isinstance(before, tuple) else (before,)
    extra = values or {}
    moved = await session.scalar(
        update(Senior)
        .where(Senior.id == senior.id, Senior.enrollment_state.in_(states))
        .values(enrollment_state=after, **extra)
        .returning(Senior.id)
    )
    if moved is None:
        await session.refresh(senior, ["enrollment_state"])
        reason = "already_done" if senior.enrollment_state == after else "wrong_state"
        log.info("refused %s: user %s, senior %s", reason, caller.user.id, senior.id)
        raise refuse(409, reason)
    await session.commit()
    await session.refresh(senior, ["enrollment_state", *extra])


def enrollments_query() -> Select:
    """GET /enrollments: waiting for DAS, by submit time (04 §1)."""
    return (
        select(Senior)
        .where(Senior.enrollment_state == EnrollmentState.submitted)
        .order_by(Senior.submitted_at.asc().nulls_first(), Senior.created_at, Senior.id)
    )


async def register(
    session: AsyncSession, caller: Caller, form: SeniorForm
) -> SeniorView:
    """A new draft for the calling medic, with the senior's own grant (UC-01)."""
    senior = Senior(medic_id=caller.user.id, **form.columns())
    session.add(senior)
    await session.flush()  # the database makes the id
    if not await sync_senior_grant(
        session,
        senior.id,
        senior.phone_e164,
        senior.full_name[:120],
        landline=senior.phone_is_landline,
        granted_by=caller.user.id,
    ):
        log.info("refused phone_taken: user %s, senior %s", caller.user.id, senior.id)
        await session.rollback()  # expires every row, so log first
        raise refuse(409, "phone_taken")
    await session.commit()
    return await senior_view(session, senior)


async def edit(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, form: SeniorForm
) -> SeniorView:
    """The registration replaced in any state; past `draft` it keeps its address
    (SE9, 04 §2)."""
    # Locked, so no move happens meanwhile
    senior = await editable_senior(session, caller, senior_id)
    missing = missing_address(form)
    if senior.enrollment_state != EnrollmentState.draft and missing:
        log.info("refused incomplete: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(422, "incomplete", missing=missing)
    was = senior.phone_e164  # the update below overwrites `senior`
    updated = await session.scalar(
        update(Senior)
        .where(Senior.id == senior_id)
        .values(**form.columns())
        .returning(Senior)
        .execution_options(populate_existing=True)
    )
    # A senior left sharing a mobile by AL7 keeps their number and stays editable
    synced = await sync_senior_grant(
        session,
        updated.id,
        updated.phone_e164,
        updated.full_name[:120],
        landline=updated.phone_is_landline,
        granted_by=caller.user.id,
    )
    if not synced and form.phone != was:
        log.info("refused phone_taken: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(409, "phone_taken")
    await session.commit()
    return await senior_view(session, updated)


async def grant_caregiver(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, form: CaregiverForm
) -> CaregiverView:
    """A caregiver grant for the number; one it already holds is `already_done`."""
    await editable_senior(session, caller, senior_id)
    user = await add_caregiver_grant(
        session, senior_id, form.phone, form.display_name, form.relation, caller.user.id
    )
    if user is None:
        await session.rollback()
        raise refuse(409, "already_done")
    note(session, Change(ChangeKind.caregivers, senior_id))
    await session.commit()
    return CaregiverView(
        user_id=user.id,
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        relation=form.relation,
    )


async def edit_caregiver(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    user_id: uuid.UUID,
    form: CaregiverEditForm,
) -> CaregiverView:
    """The caregiver's name (everywhere, Q13) and relation; a staff member's name is
    theirs to change, so it is refused (Q22)."""
    await editable_senior(session, caller, senior_id)
    row = (
        await session.execute(
            select(Grant, User)
            .join(User, User.id == Grant.user_id)
            .where(
                Grant.senior_id == senior_id,
                Grant.user_id == user_id,
                Grant.role == Role.caregiver,
            )
        )
    ).one_or_none()
    if row is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    grant, user = row
    if not await edit_caregiver_grant(
        session, user, grant, display_name=form.display_name, relation=form.relation
    ):
        log.info("refused not_allowed: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(403, "not_allowed")
    await session.commit()
    return CaregiverView(
        user_id=user.id,
        display_name=user.display_name,
        phone_e164=user.phone_e164,
        relation=grant.relation,
    )


async def revoke_caregiver(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Deletes the caregiver grant; past `draft` the last one stays (04 §2)."""
    senior = await editable_senior(session, caller, senior_id)
    await revoke_caregiver_grant(session, senior_id, user_id)
    if senior.enrollment_state != EnrollmentState.draft and not await has_caregiver(
        session, senior_id
    ):
        log.info("refused incomplete: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(422, "incomplete", missing=["caregiver"])
    note(session, Change(ChangeKind.caregivers, senior_id))
    await session.commit()


async def delete_draft(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *,
    read_first: Callable[[AsyncSession, uuid.UUID], Awaitable[str | None]]
    | None = None,
) -> str | None:
    """Deletes a draft and its consents; grants go by ON DELETE CASCADE. Any other row
    still pointing at the senior, a call for one, stops the delete (Q10, §5.4).
    `read_first` runs under the senior's lock, so its answer, the medical record PDF's
    key, can't change before the delete; it is returned."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state != EnrollmentState.draft:
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "wrong_state")
    read = await read_first(session, senior_id) if read_first else None
    # `voice` imports `seniors`, so the calls are not checked by name: the foreign key,
    # which fires as the statement runs, refuses them.
    try:
        await session.execute(delete(Consent).where(Consent.senior_id == senior_id))
        await session.execute(delete(Senior).where(Senior.id == senior_id))
        await session.commit()
    except IntegrityError:
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(409, "wrong_state") from None
    return read


async def submit(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> SeniorSummary:
    """draft -> submitted, once nothing DAS needs is missing (UC-01 step 6)."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state == EnrollmentState.draft:
        missing = await missing_to_submit(session, senior)
        if missing:
            log.info(
                "refused incomplete: user %s, senior %s", caller.user.id, senior_id
            )
            raise refuse(422, "incomplete", missing=missing)
    await move(
        session,
        caller,
        senior,
        EnrollmentState.draft,
        EnrollmentState.submitted,
        values={"submitted_at": func.now()},
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def accept(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *,
    then: Hook | None = None,
) -> SeniorSummary:
    """submitted -> accepted, by DAS (UC-04 step 1). `then` runs first and `move` commits
    both, so a refused move leaves nothing of it."""
    senior = await reach_senior(session, caller, senior_id)
    if then is not None:
        await then(session, senior.id)
    await move(
        session,
        caller,
        senior,
        EnrollmentState.submitted,
        EnrollmentState.accepted,
        values={"accepted_at": func.now(), "accepted_by": caller.user.id},
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def call_again(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *,
    then: Hook,
    pending: Callable[[AsyncSession, uuid.UUID], Awaitable[bool]],
) -> SeniorSummary:
    """Sună din nou: `wrong_number` or `unreachable` -> `accepted`, with a new welcome
    call queued in the same transaction, by the registering medic (UC-04, 04 §2). The
    number is not checked: a correct one can come back as `wrong_number`.

    A repeat, `accepted` with a welcome call already queued or live, answers the same
    and queues nothing (04 §0). `accepted` without one, or any other state, is
    `wrong_state`. `accepted_at` and `accepted_by` stay: they record DAS's acceptance.
    """
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state == EnrollmentState.accepted and await pending(
        session, senior.id
    ):
        return SeniorSummary.model_validate(senior, from_attributes=True)
    if senior.enrollment_state not in (
        EnrollmentState.wrong_number,
        EnrollmentState.unreachable,
    ):
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "wrong_state")
    await then(session, senior.id)
    # Another live call keeps the welcome call out (`uq_calls_live_senior`, 05 §3):
    # moved without one, she would wait in `accepted` for a call that never comes
    if not await pending(session, senior.id):
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(409, "wrong_state")
    await move(
        session,
        caller,
        senior,
        (EnrollmentState.wrong_number, EnrollmentState.unreachable),
        EnrollmentState.accepted,
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def withdraw_consent(
    session: AsyncSession,
    caller: Caller,
    senior_id: uuid.UUID,
    *,
    then: Hook | None = None,
) -> SeniorSummary:
    """active -> withdrawn, with a consent row for it, by the registering medic or DAS
    (Q15). The row and `then` come first and `move` commits them; a refusal commits
    none."""
    senior = await editable_senior(session, caller, senior_id)
    latest = await session.scalar(
        select(Consent.text_version)
        .where(Consent.senior_id == senior_id)
        .order_by(Consent.at.desc(), Consent.id.desc())
        .limit(1)
    )
    registering_medic = Role.medic in caller.roles and senior.medic_id == caller.user.id
    session.add(
        Consent(
            senior_id=senior_id,
            decision=ConsentDecision.withdrawn,
            method=ConsentMethod.medic if registering_medic else ConsentMethod.das,
            text_version=latest or "none",
            recorded_by=caller.user.id,
        )
    )
    # Only an active senior is moved, so only then does `then` run: for another state it
    # would touch call rows that a welcome answer holds while it waits on this senior.
    if then is not None and senior.enrollment_state is EnrollmentState.active:
        await then(session, senior.id)
    await move(
        session, caller, senior, EnrollmentState.active, EnrollmentState.withdrawn
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def save_signature(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, form: SignatureForm
) -> None:
    """A signed consent for a senior not yet active, by the registering medic. The
    latest signature counts, so a repeat adds a row (Q16)."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state not in (
        EnrollmentState.draft,
        EnrollmentState.submitted,
        EnrollmentState.accepted,
    ):
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "wrong_state")
    session.add(
        Consent(
            senior_id=senior_id,
            decision=ConsentDecision.given,
            method=ConsentMethod.signature,
            text_version=form.text_version,
            signature_strokes=form.model_dump(mode="json")["strokes"],
            recorded_by=caller.user.id,
        )
    )
    await session.commit()


async def confirm_welcome(
    session: AsyncSession,
    senior_id: uuid.UUID,
    call_id: uuid.UUID,
    *,
    given: bool,
    method: ConsentMethod,
    text_version: str,
    evidence: dict[str, Any] | None = None,
) -> bool:
    """The welcome call's answer to the consent text: `accepted` becomes `active` or
    `refused`, with its consent record (UC-02, 03 §8). `evidence` is the key or the
    words a phone call heard (G7). Doesn't commit (ADR-005).

    False, with nothing written, when the senior is no longer `accepted`: of two moves
    at once one wins (05 §3's pattern).
    """
    moved = await session.scalar(
        update(Senior)
        .where(
            Senior.id == senior_id,
            Senior.enrollment_state == EnrollmentState.accepted,
        )
        .values(
            enrollment_state=EnrollmentState.active
            if given
            else EnrollmentState.refused
        )
        .returning(Senior.id)
    )
    if moved is None:
        return False
    session.add(
        Consent(
            senior_id=senior_id,
            decision=ConsentDecision.given if given else ConsentDecision.refused,
            method=method,
            text_version=text_version,
            call_id=call_id,
            evidence=evidence,
        )
    )
    return True


async def end_welcome(
    session: AsyncSession, senior_id: uuid.UUID, state: EnrollmentState
) -> bool:
    """A welcome call that reached no consent: `accepted` becomes `wrong_number` or
    `unreachable` (UC-04). Doesn't commit (ADR-005).

    False, with nothing written, when the senior is no longer `accepted`, as for
    `confirm_welcome`.
    """
    moved = await session.scalar(
        update(Senior)
        .where(
            Senior.id == senior_id,
            Senior.enrollment_state == EnrollmentState.accepted,
        )
        .values(enrollment_state=state)
        .returning(Senior.id)
    )
    return moved is not None


async def record_check_in(
    session: AsyncSession, senior_id: uuid.UUID, form: CheckInForm, now: datetime
) -> None:
    """Stores the watch's latest check-in (UC-13). A time ahead of `now` is stored as
    `now`; a check-in older than the stored one changes nothing, since the phone may
    relay late and out of order."""
    measured_at = min(form.measured_at, now)
    check_in = insert(WatchState).values(
        senior_id=senior_id,
        state=WatchCondition.not_worn if form.worn is False else WatchCondition.ok,
        last_check_in_at=measured_at,
        battery=form.battery,
        worn=form.worn,
        last_pulse=form.last_pulse,
        resting_pulse=form.resting_pulse,
        steps_today=form.steps_today,
        minutes_without_steps=form.minutes_without_steps,
    )
    # Every check-in is a reading, a late one too; a resent one is kept once (ADR-006)
    await session.execute(
        insert(WatchReading)
        .values(
            senior_id=senior_id,
            measured_at=measured_at,
            pulse=form.last_pulse,
            resting_pulse=form.resting_pulse,
            steps_today=form.steps_today,
            battery=form.battery,
            worn=form.worn,
        )
        .on_conflict_do_nothing(index_elements=["senior_id", "measured_at"])
    )
    before = await session.scalar(
        select(WatchState.state).where(WatchState.senior_id == senior_id)
    )
    # None when the check-in was too old to be written
    after = await session.scalar(
        check_in.on_conflict_do_update(
            index_elements=[WatchState.senior_id],
            set_={
                c: check_in.excluded[c]
                for c in (
                    "state",
                    "last_check_in_at",
                    "battery",
                    "worn",
                    "last_pulse",
                    "resting_pulse",
                    "steps_today",
                    "minutes_without_steps",
                )
            },
            where=WatchState.last_check_in_at <= check_in.excluded.last_check_in_at,
        ).returning(WatchState.state)
    )
    # A watch that goes on checking in tells nobody anything new (04 §6)
    if after is not None and after != before:
        note(session, Change(ChangeKind.watch, senior_id))
    await session.commit()


def sees_watch(caller: Caller, senior_id: uuid.UUID, medic_id: uuid.UUID) -> bool:
    """Whether the caller looks after this senior, as her registering medic, as a
    caregiver (UC-12) or as DAS (ADR-006), or is the senior herself on her own page
    (UC-03). DAS reaches only seniors past `draft`; `reach_senior` checks that first."""
    is_self = any(
        g.role == Role.senior and g.senior_id == senior_id for g in caller.grants
    )
    registered = Role.medic in caller.roles and medic_id == caller.user.id
    caring = any(
        g.role == Role.caregiver and g.senior_id == senior_id for g in caller.grants
    )
    return is_self or registered or caring or Role.das in caller.roles


async def watch_state(
    session: AsyncSession, caller: Caller, senior: Senior
) -> tuple[WatchCondition | None, int | None]:
    """The watch's state and its latest pulse, for whoever `sees_watch` (UC-03, UC-12,
    ADR-006). Returns (None, None) when the caller can't see."""
    if not sees_watch(caller, senior.id, senior.medic_id):
        return None, None
    row = (
        await session.execute(
            select(WatchState.state, WatchState.last_pulse).where(
                WatchState.senior_id == senior.id
            )
        )
    ).one_or_none()
    return (row.state, row.last_pulse) if row else (None, None)


async def app_signed_in(
    session: AsyncSession, caller: Caller, senior: Senior
) -> bool | None:
    """Whether the user holding her senior grant has ever signed in, for the „Pacientul nu
    a deschis aplicația” warning (design 2026-11-14); null for who can't see her watch.
    shortcut: a sign-in in any role counts; add a "signed in as senior" time if that
    misleads in a pilot."""
    if not sees_watch(caller, senior.id, senior.medic_id):
        return None
    signed = await session.scalar(
        select(User.firebase_uid.is_not(None))
        .join(Grant, Grant.user_id == User.id)
        .where(Grant.senior_id == senior.id, Grant.role == Role.senior)
    )
    return bool(signed)  # no senior grant (a landline, AL7) is False


READINGS_KEPT = timedelta(hours=24)
# Literal SQL, so the GROUP BY renders the same text as the SELECT
BUCKET = func.date_bin(
    text("interval '5 minutes'"),
    WatchReading.measured_at,
    text("timestamptz '2000-01-01 00:00+00'"),
)


async def watch_view(
    session: AsyncSession, caller: Caller, senior: Senior
) -> WatchView | None:
    """The latest check-in (04 §1, ADR-006); None before the first one or when the
    caller can't see the watch."""
    if not sees_watch(caller, senior.id, senior.medic_id):
        return None
    row = await session.get(WatchState, senior.id)
    return WatchView.model_validate(row, from_attributes=True) if row else None


async def watch_readings(
    session: AsyncSession, caller: Caller, senior: Senior, now: datetime
) -> list[WatchReadingView]:
    """The last 24 hours in 5-minute buckets, oldest first (04 §1, ADR-006); empty when
    the caller can't see the watch."""
    if not sees_watch(caller, senior.id, senior.medic_id):
        return []
    rows = await session.execute(
        select(
            BUCKET.label("at"),
            func.round(func.avg(WatchReading.pulse)).cast(Integer).label("pulse"),
            func.min(WatchReading.battery).label("battery"),
            func.bool_and(WatchReading.worn).label("worn"),
            func.max(WatchReading.steps_today).label("steps_today"),
        )
        .where(
            WatchReading.senior_id == senior.id,
            WatchReading.measured_at >= now - READINGS_KEPT,
        )
        .group_by(BUCKET)
        .order_by(BUCKET)
    )
    return [WatchReadingView.model_validate(r, from_attributes=True) for r in rows]


async def prune_watch_readings(session: AsyncSession, now: datetime) -> int:
    """Deletes readings older than 24 hours (05 §5, ADR-006). Returns how many."""
    pruned = await session.execute(
        delete(WatchReading).where(WatchReading.measured_at < now - READINGS_KEPT)
    )
    await session.commit()
    return pruned.rowcount


def watch_silence() -> timedelta:
    """How long a watch may go without a check-in before it is `offline` (UC-13)."""
    return timedelta(seconds=90) if get_settings().demo_mode else timedelta(minutes=45)


async def silence_watches(session: AsyncSession, now: datetime) -> int:
    """Marks every watch whose check-ins stopped `offline` (UC-13); its next check-in
    puts it back. Returns how many."""
    silent = list(
        await session.scalars(
            update(WatchState)
            .where(
                WatchState.state.in_([WatchCondition.ok, WatchCondition.not_worn]),
                WatchState.last_check_in_at < now - watch_silence(),
            )
            .values(state=WatchCondition.offline)
            .returning(WatchState.senior_id)
        )
    )
    for senior_id in silent:
        note(session, Change(ChangeKind.watch, senior_id))
    await session.commit()
    if silent:
        log.info("%d watches gone offline", len(silent))
    return len(silent)


def add_summary(
    session: AsyncSession,
    *,
    senior_id: uuid.UUID,
    call_id: uuid.UUID,
    previous_id: uuid.UUID | None,
    content: SummaryContent,
    model: str,
) -> None:
    """A new version; the caller commits (design §4)."""
    session.add(
        SummaryVersion(
            senior_id=senior_id,
            call_id=call_id,
            previous_id=previous_id,
            content=content.model_dump(mode="json"),
            model=model,
        )
    )


async def latest_summary(
    session: AsyncSession, senior_id: uuid.UUID
) -> SummaryVersion | None:
    return await session.scalar(
        select(SummaryVersion)
        .where(SummaryVersion.senior_id == senior_id)
        .order_by(SummaryVersion.created_at.desc(), SummaryVersion.id.desc())
        .limit(1)
    )


def read_content(version: SummaryVersion) -> SummaryContent | None:
    """None when the stored JSON no longer fits the shape; logs the id, never the text."""
    try:
        return SummaryContent.model_validate(version.content)
    except ValidationError:
        log.warning("summary %s no longer validates", version.id)
        return None


def summary_view(version: SummaryVersion | None) -> SummaryVersionView | None:
    """None when there is no version or its JSON is stale: no briefing either way."""
    content = version and read_content(version)
    if version is None or content is None:
        return None
    return SummaryVersionView(
        content=content, call_id=version.call_id, created_at=version.created_at
    )


async def summary_for(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> SummaryVersionView | None:
    """The briefing for the senior's registering medic and DAS past `draft`; the
    caregiver and the senior get 404 like a stranger (04 §1, design §5 B)."""
    reached = await session.scalar(
        select(Senior.id).where(
            Senior.id == senior_id,
            or_(reach(caller, Role.medic), reach(caller, Role.das)),
        )
    )
    if reached is None:
        log.info("refused not_found: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(404, "not_found")
    return summary_view(await latest_summary(session, senior_id))


async def erase_senior_children(session: AsyncSession, senior_id: uuid.UUID) -> None:
    """The senior's consents, summaries and watch data, for an erasure (design
    2026-11-14). Doesn't commit (ADR-005)."""
    for model in (Consent, SummaryVersion, WatchReading, WatchState):
        await session.execute(delete(model).where(model.senior_id == senior_id))


async def erase_senior_row(session: AsyncSession, senior_id: uuid.UUID) -> None:
    """The senior's row, last; its grants go by ON DELETE CASCADE (design 2026-11-14).
    Doesn't commit (ADR-005)."""
    await session.execute(delete(Senior).where(Senior.id == senior_id))
