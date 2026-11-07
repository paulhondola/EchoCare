"""Seed the demo cast: a medic, a DAS employee on duty, and a senior the medic registered
with a caregiver, submitted for DAS to accept (ADR-001: staging holds the team's phones,
production the demo cast). DAS pressing „Acceptă” then rings the senior's welcome call.

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
from typing import Any, Self

# Run as a file, Python puts scripts/ on the path, not the folder that holds app/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError, model_validator
from sqlalchemy import select

from app.auth.schemas import StaffGrantForm
from app.auth.service import Caller, grant_staff, set_on_duty
from app.core.db import Session
from app.core.phones import mask
from app.core.settings import db_host, get_settings, is_local_db, on_railway
from app.models import EnrollmentState, Grant, Role, Senior, User
from app.seniors.schemas import CaregiverForm, SeniorForm
from app.seniors.service import grant_caregiver, register, submit


class Cast(BaseModel):
    """The four people, each checked as the API checks them (POST /staff, /seniors,
    /seniors/{id}/caregivers); the role of each staff entry comes from its key."""

    medic: StaffGrantForm
    das: StaffGrantForm
    senior: SeniorForm
    caregiver: CaregiverForm

    @model_validator(mode="before")
    @classmethod
    def staff_roles(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for role in ("medic", "das"):
                if isinstance(data.get(role), dict):
                    data = {**data, role: {**data[role], "role": role}}
        return data

    @model_validator(mode="after")
    def senior_can_be_submitted(self) -> Self:
        # Submitting needs the address (UC-01 step 6); a draft would wait forever.
        if not (self.senior.street and self.senior.street_number):
            raise ValueError(
                "the senior needs street and street_number to be submitted"
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


async def seed_cast(cast: Cast) -> list[str]:
    """Seeds the cast through the same steps the apps take; what it did, one line each.
    Each step commits, so a run that stops halfway is finished by the next one."""
    lines = []
    async with Session() as session:
        medic_id, said = await staff(session, cast.medic)
        lines.append(said)
        das_id, said = await staff(session, cast.das)
        lines.append(said)
        await set_on_duty(session, das_id)
        lines.append(f"on duty: {cast.das.display_name}")

        medic = await session.get(User, medic_id, populate_existing=True)
        grants = list(
            await session.scalars(select(Grant).where(Grant.user_id == medic_id))
        )
        caller = Caller(medic, grants)
        senior = await session.scalar(
            select(Senior)
            .where(Senior.phone_e164 == cast.senior.phone)
            .order_by(Senior.created_at)
        )
        name = f"{cast.senior.form_of_address} ({mask(cast.senior.phone)})"
        if senior is not None and senior.medic_id != medic_id:
            lines.append(f"senior {name}: registered by another medic, left as it is")
            return lines
        if senior is None:
            senior_id = (await register(session, caller, cast.senior)).id
        else:
            senior_id = senior.id
        try:
            await grant_caregiver(session, caller, senior_id, cast.caregiver)
        except HTTPException as e:
            if e.detail.get("reason") != "already_done":
                raise
        state = await session.scalar(
            select(Senior.enrollment_state).where(Senior.id == senior_id)
        )
        if state is EnrollmentState.draft:
            await submit(session, caller, senior_id)
            lines.append(f"senior submitted: {name}, for DAS to accept")
        else:
            lines.append(f"senior {name}: already {state.value}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed the demo cast (medic, DAS, senior, caregiver) from a JSON file."
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
