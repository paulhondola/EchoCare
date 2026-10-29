"""scripts/seed_cast.py: the demo cast for staging and production (ADR-001, #48)."""

import io
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.settings import get_settings
from app.models import EnrollmentState, Grant, Role, Senior, User
from scripts.seed_cast import Cast, check_target, read_cast, seed_cast

EXAMPLE = Path(__file__).resolve().parents[2] / "cast.example.json"

CAST = {
    "medic": {
        "display_name": "Medic Cast",
        "phone": "0700 000 201",
        "practice": "CMI Test",
    },
    "das": {"display_name": "DAS Cast", "phone": "+40700000202"},
    "senior": {
        "full_name": "Senior Cast",
        "form_of_address": "domnul Test",
        "phone": "+40700000203",
        "street": "Strada Test",
        "street_number": "1",
    },
    "caregiver": {
        "display_name": "Aparținător Cast",
        "relation": "fiul",
        "phone": "+40700000204",
    },
}


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


async def user(db, phone: str) -> User:
    return await db.scalar(
        select(User)
        .where(User.phone_e164 == phone)
        .execution_options(populate_existing=True)
    )


async def roles(db, phone: str) -> set[Role]:
    rows = await db.scalars(
        select(Grant.role)
        .join(User, User.id == Grant.user_id)
        .where(User.phone_e164 == phone)
    )
    return {Role(r) for r in rows}


async def test_the_cast_is_seeded_once(db):
    first = await seed_cast(Cast.model_validate(CAST))
    users, grants, seniors = (
        await count(db, User),
        await count(db, Grant),
        await count(db, Senior),
    )
    second = await seed_cast(Cast.model_validate(CAST))

    medic, das = await user(db, "+40700000201"), await user(db, "+40700000202")
    assert (medic.display_name, medic.practice) == ("Medic Cast", "CMI Test")
    assert await roles(db, "+40700000201") == {Role.medic}
    assert await roles(db, "+40700000202") == {Role.das}
    assert das.on_duty
    senior = await db.scalar(select(Senior).where(Senior.phone_e164 == "+40700000203"))
    assert (senior.form_of_address, senior.enrollment_state, senior.medic_id) == (
        "domnul Test",
        EnrollmentState.submitted,
        medic.id,
    )
    # Each signs in to their own role: the senior and the caregiver too (AL7).
    assert await roles(db, "+40700000203") == {Role.senior}
    assert await roles(db, "+40700000204") == {Role.caregiver}

    assert (await count(db, User), await count(db, Grant), await count(db, Senior)) == (
        users,
        grants,
        seniors,
    )
    assert "granted" in first[0] and "already" in second[0]
    assert first[-1].startswith("senior submitted") and "already" in second[-1]
    # Numbers are masked in what it prints (auth-layer AL15).
    assert not any("+40700000203" in line for line in first + second)


async def test_a_number_another_medic_registered_is_left_alone(db, add_senior):
    theirs = await add_senior("+40700000203", name="Altcineva")
    lines = await seed_cast(Cast.model_validate(CAST))
    assert "left as it is" in lines[-1]
    senior = await db.get(Senior, theirs.id, populate_existing=True)
    assert (senior.full_name, senior.enrollment_state) == (
        "Altcineva",
        EnrollmentState.draft,
    )
    assert await roles(db, "+40700000202") == {Role.das}  # the rest is still seeded


def test_a_cloud_database_is_refused_from_a_laptop(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    with pytest.raises(SystemExit, match="inside the api container"):
        check_target("staging")


def test_inside_railway_confirm_must_name_the_environment(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.setattr(s, "app_env", "production")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "d-1")
    for confirm in (None, "staging"):
        with pytest.raises(SystemExit, match="--confirm production"):
            check_target(confirm)
    assert "production" in check_target("production")


def test_a_local_database_needs_no_confirm():
    assert "local" in check_target(None)


@pytest.mark.parametrize(
    "change",
    [
        {"das": {"display_name": "DAS", "phone": "0256 123 456"}},  # a landline
        {"medic": {"display_name": "Medic", "phone": "+40700000201"}},  # no practice
        {"senior": {"full_name": "Fără adresă", "phone": "+40700000203"}},
    ],
)
def test_a_bad_cast_is_refused(tmp_path, change):
    path = tmp_path / "cast.json"
    path.write_text(json.dumps({**CAST, **change}))
    with pytest.raises(SystemExit, match="cast"):
        read_cast(str(path))


def test_the_cast_can_come_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(CAST)))
    assert read_cast("-").senior.full_name == "Senior Cast"


def test_the_example_cast_is_valid_and_made_up():
    cast = read_cast(str(EXAMPLE))
    phones = [cast.medic.phone, cast.das.phone, cast.senior.phone, cast.caregiver.phone]
    # Real numbers never enter Git (#48): only Firebase's test range here.
    assert all(p.startswith("+40700000") for p in phones)
