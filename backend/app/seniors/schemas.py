import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.phones import is_mobile, normalize
from app.seniors.models import WatchCondition


class SeniorDetail(BaseModel):
    """Registration, address and access details (G13)."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    phone_e164: str
    phone_is_landline: bool
    street: str | None
    street_number: str | None
    block: str | None
    staircase: str | None
    floor: str | None
    apartment: str | None
    intercom_code: str | None
    key_holder: str | None
    landmark: str | None


class CaregiverSummary(BaseModel):
    display_name: str
    phone_e164: str
    relation: str | None


def no_nul(value: str) -> str:
    # Postgres text cannot hold a NUL. Refuse it here, as a 422, not there, as a 500.
    if "\x00" in value:
        raise ValueError("the text contains a NUL character")
    return value


def text(max_length: int, min_length: int = 0) -> Any:
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
        AfterValidator(no_nul),
    ]


# Enrollment states read back as their names; an unknown one as the bare string.
State = Annotated[str, BeforeValidator(lambda v: getattr(v, "value", v))]

# A code reads back as its name ("green"): Severity is an IntEnum and would serialize as 0.
Code = Annotated[str, BeforeValidator(lambda v: getattr(v, "name", v))]

# The registration form's optional fields (UC-01 steps 1 and 2); empty means none.
OPTIONAL = (
    "call_window",
    "street",
    "street_number",
    "block",
    "staircase",
    "floor",
    "apartment",
    "intercom_code",
    "key_holder",
    "landmark",
)


class SeniorForm(BaseModel):
    """POST /seniors and PUT /seniors/{id}'s body: the whole registration (UC-01)."""

    full_name: text(200, 1)
    form_of_address: text(120, 1)  # "doamna Maria"
    phone: str  # a landline or a mobile; which is worked out from the number
    call_window: text(60) | None = None
    street: text(200) | None = None
    street_number: text(20) | None = None
    block: text(20) | None = None
    staircase: text(20) | None = None
    floor: text(20) | None = None
    apartment: text(20) | None = None
    intercom_code: text(40) | None = None
    key_holder: text(200) | None = None
    landmark: text(200) | None = None

    @field_validator("phone")
    @classmethod
    def e164(cls, raw: str) -> str:
        return normalize(raw)

    @field_validator(*OPTIONAL)
    @classmethod
    def empty_is_none(cls, value: str | None) -> str | None:
        # A form's empty field stores nothing, not "".
        return value or None

    def columns(self) -> dict[str, Any]:
        return {
            **self.model_dump(exclude={"phone"}),
            "phone_e164": self.phone,
            "phone_is_landline": not is_mobile(self.phone),
        }


class CaregiverForm(BaseModel):
    """POST /seniors/{id}/caregivers's body (UC-01 step 3)."""

    display_name: text(120, 1)
    relation: text(60, 1)  # "fiica"
    phone: str

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("caregivers sign in by SMS: the number must be a mobile")
        return e164


class CaregiverEditForm(BaseModel):
    """PATCH /seniors/{id}/caregivers/{userId}'s body: what is given changes (Q13)."""

    display_name: text(120, 1) | None = None
    relation: text(60, 1) | None = None


MAX_SIGNATURE_POINTS = 5000

# A point on the signature pad, as a share of its width and height.
Coordinate = Annotated[float, Field(ge=0, le=1)]


class SignatureForm(BaseModel):
    """POST /seniors/{id}/signature's body: the strokes the senior drew (Q16)."""

    text_version: text(40, 1)
    strokes: Annotated[
        list[Annotated[list[tuple[Coordinate, Coordinate]], Field(min_length=1)]],
        Field(min_length=1),
    ]

    @model_validator(mode="after")
    def not_too_many_points(self) -> Self:
        if sum(len(stroke) for stroke in self.strokes) > MAX_SIGNATURE_POINTS:
            raise ValueError(f"at most {MAX_SIGNATURE_POINTS} points in total")
        return self


class SeniorSummary(BaseModel):
    """One row of GET /seniors (04 §1), with the fields that exist today."""

    id: uuid.UUID
    full_name: str
    form_of_address: str
    # The number and whether it is a landline, for the apps' senior cards (seniors §3.3).
    phone_e164: str
    phone_is_landline: bool
    enrollment_state: State
    # The current code (Q17), null until the first result and for a senior not `active`.
    code: Code | None = None
    reason: str | None = None
    since: datetime | None = None


class CaregiverView(CaregiverSummary):
    user_id: uuid.UUID  # for DELETE /seniors/{id}/caregivers/{userId}


class MedicView(BaseModel):
    """The medic who registered the senior, on the senior's page (seniors §3.3)."""

    display_name: str
    practice: str | None


class SeniorView(SeniorDetail):
    """GET /seniors/{id} (04 §1): registration, address, medic and caregivers. One
    shape for every role (seniors SE7)."""

    call_window: str | None
    enrollment_state: State
    code: Code | None = None
    reason: str | None = None
    since: datetime | None = None
    # True while one of her calls rings or is live, for the badge (UC-12). Set by
    # GET /seniors/{id} only; null on the other answers that carry the senior.
    call_in_progress: bool | None = None
    # `ok`, `not_worn` or `offline`, for her caregivers and her medic (UC-12). Set by
    # GET /seniors/{id} only; null also before the watch's first check-in.
    watch_state: WatchCondition | None = None
    medic: MedicView
    caregivers: list[CaregiverView]


class CheckInForm(BaseModel):
    """The watch's latest reading, relayed by the senior's phone (UC-13). `measured_at`
    carries an offset: a naive time is 422."""

    measured_at: AwareDatetime
    battery: int | None = Field(None, ge=0, le=100)
    worn: bool | None = None
    last_pulse: int | None = Field(None, ge=0, le=300)
