"""Seed the demo cast: staff, each with one or both of das and medic, exactly one DAS on
duty, and seniors their medic registered with caregivers, submitted for DAS to accept
(ADR-001: staging holds the team's phones, production the demo cast). A caregiver may
also be staff. DAS pressing „Acceptă” then rings the senior's welcome call.

The cast is real people, so it never enters Git (#48). It comes from a JSON file kept
outside the repository, or as the git-ignored backend/cast.json; cast.example.json shows
its shape. Read from a path, or from stdin with "-". Locally, from backend/:

    uv run python scripts/seed_cast.py ../../echocare-cast.json

On Railway, inside the api container, the file piped in from the laptop:

    railway ssh -s api -e staging -- python scripts/seed_cast.py --confirm staging - < cast.json

A second run adds nothing. A cloud database is refused from a laptop, and inside a Railway
deployment `--confirm` must name its APP_ENV, so production is never seeded by mistake.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import Annotated, Literal, Self

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select

from app.auth.schemas import StaffGrantForm
from app.auth.service import Caller, grant_staff, set_on_duty
from app.core.db import Session
from app.core.phones import mask, normalize
from app.core.settings import db_host, get_settings, is_local_db, on_railway
from app.models import EnrollmentState, Grant, Role, Senior, User
from app.seniors.schemas import CaregiverForm, SeniorForm
from app.seniors.service import grant_caregiver, register, submit


class StaffEntry(BaseModel):
    """One staff member with one or both staff roles (grants are unique per user and
    role, so das and medic can share a number). Each role is checked as POST /staff
    checks it; the medic's practice is ignored for das."""

    display_name: str
    phone: str
    roles: Annotated[list[Literal["das", "medic"]], Field(min_length=1, max_length=2)]
    practice: str | None = None
    on_duty: bool = False

    @field_validator("roles")
    @classmethod
    def no_repeats(cls, roles: list[str]) -> list[str]:
        if len(set(roles)) != len(roles):
            raise ValueError("a role is named twice")
        return roles

    @model_validator(mode="after")
    def staff_forms(self) -> Self:
        self.phone = self.forms()[0].phone  # E.164, as the forms normalize it
        if self.on_duty and "das" not in self.roles:
            raise ValueError("only a das can be on duty")
        return self

    def forms(self) -> list[StaffGrantForm]:
        return [
            StaffGrantForm(
                display_name=self.display_name,
                phone=self.phone,
                role=role,
                practice=self.practice,
            )
            for role in self.roles
        ]


class SeniorEntry(SeniorForm):
    """A senior as POST /seniors checks them, the staff phone of their medic, and their
    caregivers as POST /seniors/{id}/caregivers checks each."""

    medic: str
    caregivers: list[CaregiverForm] = Field(default_factory=list)

    @field_validator("medic")
    @classmethod
    def medic_e164(cls, raw: str) -> str:
        return normalize(raw)

    def form(self) -> SeniorForm:
        return SeniorForm(**self.model_dump(exclude={"medic", "caregivers"}))


class Cast(BaseModel):
    """Staff and seniors, who name each other by phone (ADR-001: staging holds the
    team's phones, production the demo cast)."""

    staff: Annotated[list[StaffEntry], Field(min_length=1)]
    seniors: list[SeniorEntry] = []

    @model_validator(mode="after")
    def people_fit(self) -> Self:
        phones = [s.phone for s in self.staff]
        if len(set(phones)) != len(phones):
            raise ValueError("two staff entries share a phone")
        # One on duty: the hand-over rings that person (set_on_duty, 06 §4).
        if sum(s.on_duty for s in self.staff) != 1:
            raise ValueError("exactly one das must be on_duty")
        medics = {s.phone for s in self.staff if "medic" in s.roles}
        for senior in self.seniors:
            if senior.medic not in medics:
                raise ValueError(
                    f"{senior.form_of_address}: medic is not a staff medic in the cast"
                )
            # Submitting needs the address (UC-01 step 6); a draft would wait forever.
            if not (senior.street and senior.street_number):
                raise ValueError(
                    f"{senior.form_of_address} needs street and street_number to be "
                    "submitted"
                )
        return self


def check_target(confirm: str | None) -> str:
    """Which database this is, or SystemExit: a cloud one only from inside its Railway
    deployment (as alembic/env.py), and only when `confirm` names its APP_ENV."""
    s = get_settings()
    host = db_host(s.database_url)
    if is_local_db(s.database_url):
        return f"local database {host}"
    if not on_railway():
        raise SystemExit(
            f"Refusing to seed {host} from outside Railway: run it inside the api "
            "container (railway ssh -s api -e <environment> -- python scripts/...)."
        )
    if confirm != s.app_env:
        raise SystemExit(
            f"This is {s.app_env}: run again with --confirm {s.app_env} to seed it."
        )
    return f"{s.app_env} database {host}"


def read_cast(source: str) -> Cast:
    """The cast from a JSON file, or stdin for "-"; SystemExit naming what is wrong."""
    try:
        text = sys.stdin.read() if source == "-" else Path(source).read_text()
        return Cast.model_validate_json(text)
    except OSError as e:
        raise SystemExit(f"Cannot read the cast: {e}") from e
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()
        )
        raise SystemExit(f"The cast is not valid: {problems}") from e


async def staff(session, form: StaffGrantForm) -> tuple[uuid.UUID, str]:
    """The grant, and the user's id: an id, not the row, since a grant already held
    rolls the session back, which expires every row loaded before it."""
    role = Role(form.role)
    granted = await grant_staff(
        session, form.display_name, form.phone, role, form.practice, None
    )
    user_id = await session.scalar(select(User.id).where(User.phone_e164 == form.phone))
    said = "granted" if granted else "already granted"
    return user_id, f"{role.value} {form.display_name} ({mask(form.phone)}): {said}"


async def senior(session, entry: SeniorEntry, medic_id: uuid.UUID) -> str:
    """Registers, gives caregivers and submits one senior as their medic; what it did."""
    medic = await session.get(User, medic_id, populate_existing=True)
    grants = list(await session.scalars(select(Grant).where(Grant.user_id == medic_id)))
    caller = Caller(medic, grants)
    found = await session.scalar(
        select(Senior)
        .where(Senior.phone_e164 == entry.phone)
        .order_by(Senior.created_at)
    )
    name = f"{entry.form_of_address} ({mask(entry.phone)})"
    if found is not None and found.medic_id != medic_id:
        return f"senior {name}: registered by another medic, left as it is"
    if found is None:
        senior_id = (await register(session, caller, entry.form())).id
    else:
        senior_id = found.id
    for caregiver in entry.caregivers:
        try:
            await grant_caregiver(session, caller, senior_id, caregiver)
        except HTTPException as e:
            if e.detail.get("reason") != "already_done":
                raise
    state = await session.scalar(
        select(Senior.enrollment_state).where(Senior.id == senior_id)
    )
    if state is EnrollmentState.draft:
        await submit(session, caller, senior_id)
        return f"senior submitted: {name}, for DAS to accept"
    return f"senior {name}: already {state.value}"


async def seed_cast(cast: Cast) -> list[str]:
    """Seeds the cast through the same steps the apps take; what it did, one line each.
    Each step commits, so a run that stops halfway is finished by the next one."""
    lines = []
    users: dict[str, uuid.UUID] = {}
    async with Session() as session:
        for entry in cast.staff:
            for form in entry.forms():
                users[entry.phone], said = await staff(session, form)
                lines.append(said)
        duty = next(s for s in cast.staff if s.on_duty)
        await set_on_duty(session, users[duty.phone])
        lines.append(f"on duty: {duty.display_name}")
        for entry in cast.seniors:
            lines.append(await senior(session, entry, users[entry.medic]))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the demo cast (staff and seniors) from a JSON file."
    )
    parser.add_argument("cast", help='the cast JSON file, or "-" for stdin')
    parser.add_argument(
        "--confirm", help="the APP_ENV of the cloud database being seeded"
    )
    args = parser.parse_args()
    target = check_target(args.confirm)
    cast = read_cast(args.cast)
    print(f"Seeding the cast into the {target}")
    for line in asyncio.run(seed_cast(cast)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
