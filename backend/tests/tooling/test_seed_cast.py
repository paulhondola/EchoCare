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
    "staff": [
        {
            "display_name": "DAS Medic Cast",
            "phone": "0700 000 201",
            "roles": ["das", "medic"],
            "practice": "CMI Test",
            "on_duty": True,
        },
        {"display_name": "DAS Cast", "phone": "+40700000202", "roles": ["das"]},
    ],
    "seniors": [
        {
            "full_name": "Senior Cast",
            "form_of_address": "domnul Test",
            "phone": "+40700000203",
            "street": "Strada Test",
            "street_number": "1",
            "medic": "+40700000201",
            "caregivers": [
                {
                    "display_name": "DAS Cast",
                    "relation": "fiul",
                    "phone": "+40700000202",
                }
            ],
        },
        {
            "full_name": "Senioară Cast",
            "form_of_address": "doamna Test",
            "phone": "+40700000205",
            "street": "Strada Test",
            "street_number": "2",
            "medic": "+40700000201",
            "caregivers": [
                {
                    "display_name": "Aparținător Cast",
                    "relation": "fiica",
                    "phone": "+40700000204",
                }
            ],
        },
    ],
}


def changed(**edits) -> dict:
    """CAST with deep edits: `staff_1={"on_duty": True}` merges into staff[1]."""
    cast = json.loads(json.dumps(CAST))
    for key, value in edits.items():
        group, index = key.rsplit("_", 1)
        cast[group][int(index)].update(value)
    return cast


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
    counts = (await count(db, User), await count(db, Grant), await count(db, Senior))
    second = await seed_cast(Cast.model_validate(CAST))

    a, b = await user(db, "+40700000201"), await user(db, "+40700000202")
    assert (a.display_name, a.practice) == ("DAS Medic Cast", "CMI Test")
    # One person may hold das and medic, another das and caregiver (grants are unique
    # per user, role and senior).
    assert await roles(db, "+40700000201") == {Role.das, Role.medic}
    assert await roles(db, "+40700000202") == {Role.das, Role.caregiver}
    assert a.on_duty and not b.on_duty
    for phone in ("+40700000203", "+40700000205"):
        senior = await db.scalar(select(Senior).where(Senior.phone_e164 == phone))
        assert (senior.enrollment_state, senior.medic_id) == (
            EnrollmentState.submitted,
            a.id,
        )
        # Each signs in to their own role (AL7).
        assert await roles(db, phone) == {Role.senior}
    assert await roles(db, "+40700000204") == {Role.caregiver}

    assert (
        await count(db, User),
        await count(db, Grant),
        await count(db, Senior),
    ) == counts
    assert any("submitted" in line for line in first)
    assert any("already" in line for line in second)
    # Numbers are masked in what it prints (auth-layer AL15).
    assert not any(
        phone in line
        for line in first + second
        for phone in ("+40700000203", "+40700000205")
    )


async def test_a_number_another_medic_registered_is_left_alone(db, add_senior):
    theirs = await add_senior("+40700000203", name="Altcineva")
    lines = await seed_cast(Cast.model_validate(CAST))
    assert any("left as it is" in line for line in lines)
    senior = await db.get(Senior, theirs.id, populate_existing=True)
    assert (senior.full_name, senior.enrollment_state) == (
        "Altcineva",
        EnrollmentState.draft,
    )
    # The rest is still seeded: the other senior and both staff.
    other = await db.scalar(select(Senior).where(Senior.phone_e164 == "+40700000205"))
    assert other.enrollment_state is EnrollmentState.submitted
    assert await roles(db, "+40700000202") == {Role.das}


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
    "cast",
    [
        changed(staff_1={"phone": "0256 123 456"}),  # a landline
        changed(staff_0={"practice": None}),  # a medic with no practice
        changed(staff_0={"on_duty": False}),  # nobody on duty
        changed(staff_1={"on_duty": True}),  # two on duty
        changed(seniors_0={"medic": "+40700000202"}),  # not a medic
        changed(seniors_0={"street_number": None}),  # cannot be submitted
        changed(staff_1={"phone": "+40700000201"}),  # one phone twice
    ],
)
def test_a_bad_cast_is_refused(tmp_path, cast):
    path = tmp_path / "cast.json"
    path.write_text(json.dumps(cast))
    with pytest.raises(SystemExit, match="cast"):
        read_cast(str(path))


def test_the_cast_can_come_from_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(CAST)))
    assert read_cast("-").seniors[0].full_name == "Senior Cast"


def test_the_example_cast_is_valid_and_made_up():
    cast = read_cast(str(EXAMPLE))
    phones = [s.phone for s in cast.staff]
    for senior in cast.seniors:
        phones += [senior.phone, senior.medic, *(c.phone for c in senior.caregivers)]
    # Real numbers never enter Git (#48): only Firebase's test range here.
    assert phones and all(p.startswith("+40700000") for p in phones)
