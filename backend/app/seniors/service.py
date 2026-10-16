import logging
import uuid

from sqlalchemy import ColumnElement, Select, delete, false, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Grant, Role, User
from app.auth.service import Caller, refuse
from app.seniors.models import (
    Consent,
    ConsentDecision,
    ConsentMethod,
    EnrollmentState,
    Senior,
)
from app.seniors.schemas import (
    CaregiverEditForm,
    CaregiverForm,
    CaregiverView,
    MedicView,
    SeniorForm,
    SeniorSummary,
    SeniorView,
    SignatureForm,
)
from app.staff.service import user_for

log = logging.getLogger("echocare.seniors")


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


async def reach_senior(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID, *, lock: bool = False
) -> Senior:
    """The senior, if the caller reaches them; otherwise 404 `not_found` (AL8).

    `lock` is FOR NO KEY UPDATE, not FOR UPDATE: inserting a grant, a call or an
    incident takes FOR KEY SHARE on the senior's row through its foreign key, which a
    plain FOR UPDATE would block (seniors §6.2).
    """
    query = select(Senior).where(Senior.id == senior_id, reach(caller))
    if lock:
        query = query.with_for_update(key_share=True)
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
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> Senior:
    """A senior the caller may edit: the registering medic, or DAS within reach (SE9).

    Locked like `own_senior`, so edits and caregiver changes on one senior run one at
    a time. Out of reach is 404; reached but neither the registering medic nor DAS
    past `draft` is 403 `not_allowed`.
    """
    senior = await reach_senior(session, caller, senior_id, lock=True)
    registering_medic = Role.medic in caller.roles and senior.medic_id == caller.user.id
    # SE9: DAS edits what she reaches as DAS, past draft; a caregiver grant is not that
    reaches_as_das = (
        Role.das in caller.roles and senior.enrollment_state != EnrollmentState.draft
    )
    if not registering_medic and not reaches_as_das:
        log.info("refused not_allowed: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(403, "not_allowed")
    return senior


async def sync_senior_grant(session: AsyncSession, senior: Senior) -> bool:
    """A mobile number is the senior's own grant; a landline has none (UC-01 step 3).

    A changed number drops the old number's grant. Returns whether the senior holds
    its number's grant afterwards: `True` for a landline, `False` when the number
    already holds another senior's, which the caller refuses as `phone_taken` (SE10).
    """
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior.id,
            Grant.role == Role.senior,
            Grant.user_id.not_in(
                select(User.id).where(User.phone_e164 == senior.phone_e164)
            ),
        )
    )
    if senior.phone_is_landline:
        return True
    user = await user_for(session, senior.phone_e164, senior.full_name[:120])
    # No conflict target: covers both the per-senior key and the SE10 index.
    await session.execute(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.senior,
            senior_id=senior.id,
            granted_by=senior.medic_id,
        )
        .on_conflict_do_nothing()
    )
    return await session.scalar(
        select(
            select(Grant.id)
            .where(
                Grant.user_id == user.id,
                Grant.senior_id == senior.id,
                Grant.role == Role.senior,
            )
            .exists()
        )
    )


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


async def senior_view(session: AsyncSession, senior: Senior) -> SeniorView:
    medic = await session.get(User, senior.medic_id)
    caregivers = (await session.execute(caregivers_query(senior.id))).mappings()
    fields = SeniorView.model_fields.keys() - {"medic", "caregivers"}
    return SeniorView(
        **{name: getattr(senior, name) for name in fields},
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
    before: EnrollmentState,
    after: EnrollmentState,
) -> None:
    """`before` -> `after`, only where the senior is still `before`, so of two at once
    one wins (05 §3's pattern). Already `after` is `already_done`, anything else
    `wrong_state`; either way nothing changes (04 §0)."""
    moved = await session.scalar(
        update(Senior)
        .where(Senior.id == senior.id, Senior.enrollment_state == before)
        .values(enrollment_state=after)
        .returning(Senior.id)
    )
    if moved is None:
        await session.refresh(senior, ["enrollment_state"])
        reason = "already_done" if senior.enrollment_state == after else "wrong_state"
        log.info("refused %s: user %s, senior %s", reason, caller.user.id, senior.id)
        raise refuse(409, reason)
    await session.commit()
    await session.refresh(senior, ["enrollment_state"])


def enrollments_query() -> Select:
    """GET /enrollments: waiting for DAS, oldest registration first (04 §1)."""
    return (
        select(Senior)
        .where(Senior.enrollment_state == EnrollmentState.submitted)
        .order_by(Senior.created_at, Senior.id)
    )


async def register(
    session: AsyncSession, caller: Caller, form: SeniorForm
) -> SeniorView:
    """A new draft for the calling medic, with the senior's own grant (UC-01)."""
    senior = Senior(medic_id=caller.user.id, **form.columns())
    session.add(senior)
    await session.flush()  # the database makes the id
    if not await sync_senior_grant(session, senior):
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
    if not await sync_senior_grant(session, updated) and form.phone != was:
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
    user = await user_for(session, form.phone, form.display_name)
    granted = await session.scalar(
        insert(Grant)
        .values(
            user_id=user.id,
            role=Role.caregiver,
            senior_id=senior_id,
            relation=form.relation,
            granted_by=caller.user.id,
        )
        .on_conflict_do_nothing()
        .returning(Grant.id)
    )
    if granted is None:
        await session.rollback()
        raise refuse(409, "already_done")
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
    if form.display_name is not None:
        staff = select(Grant.id).where(
            Grant.user_id == user_id, Grant.role.in_((Role.das, Role.medic))
        )
        if await session.scalar(select(staff.exists())):
            log.info(
                "refused not_allowed: user %s, senior %s", caller.user.id, senior_id
            )
            raise refuse(403, "not_allowed")
        user.display_name = form.display_name
    if form.relation is not None:
        grant.relation = form.relation
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
    await session.execute(
        delete(Grant).where(
            Grant.senior_id == senior_id,
            Grant.user_id == user_id,
            Grant.role == Role.caregiver,
        )
    )
    if senior.enrollment_state != EnrollmentState.draft and not await has_caregiver(
        session, senior_id
    ):
        log.info("refused incomplete: user %s, senior %s", caller.user.id, senior_id)
        await session.rollback()  # expires every row, so log first
        raise refuse(422, "incomplete", missing=["caregiver"])
    await session.commit()


async def delete_draft(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> None:
    """Deletes a draft and its consents; grants go by ON DELETE CASCADE. Any other row
    still pointing at the senior, a call for one, stops the delete (Q10, §5.4)."""
    senior = await own_senior(session, caller, senior_id)
    if senior.enrollment_state != EnrollmentState.draft:
        log.info("refused wrong_state: user %s, senior %s", caller.user.id, senior_id)
        raise refuse(409, "wrong_state")
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
        session, caller, senior, EnrollmentState.draft, EnrollmentState.submitted
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def accept(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> SeniorSummary:
    """submitted -> accepted, by DAS (UC-04 step 1)."""
    senior = await reach_senior(session, caller, senior_id)
    await move(
        session, caller, senior, EnrollmentState.submitted, EnrollmentState.accepted
    )
    return SeniorSummary.model_validate(senior, from_attributes=True)


async def withdraw_consent(
    session: AsyncSession, caller: Caller, senior_id: uuid.UUID
) -> SeniorSummary:
    """active -> withdrawn, with a consent row for it, by the registering medic or DAS
    (Q15). The row is added first and `move` commits both; a refusal commits neither."""
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
