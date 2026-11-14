import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

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

# The text signed on the medic's tablet: the welcome card's wording, closing on the
# signature instead of the question (G7, 04 §2). The app carries a copy; a change to
# either is a new version, which the server must learn before it accepts it.
SIGNATURE_CONSENT_VERSION = "v1-semnatura"
SIGNATURE_CONSENT_TEXT = (
    "Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. "
    "Ce spuneți în apel văd medicul de familie, familia și DAS. Puteți renunța oricând. "
    "Semnând mai jos, sunteți de acord."
)

# A point on the signature pad, as a share of its width and height.
Coordinate = Annotated[float, Field(ge=0, le=1)]


class SignatureForm(BaseModel):
    """POST /seniors/{id}/signature's body: the strokes the senior drew (Q16)."""

    text_version: text(40, 1)
    strokes: Annotated[
        list[Annotated[list[tuple[Coordinate, Coordinate]], Field(min_length=1)]],
        Field(min_length=1),
    ]

    @field_validator("text_version")
    @classmethod
    def known_version(cls, version: str) -> str:
        if version != SIGNATURE_CONSENT_VERSION:
            raise ValueError(f"unknown consent text version {version!r}")
        return version

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
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    # For her medic and caregivers only, null for anyone else and before the first
    # check-in (UC-12, 04 §1). Answers that build a row without the join leave it null.
    watch_state: WatchCondition | None = None
    # The medical record's state, for the senior's registering medic only; null for anyone
    # else and when no record is attached (04 §1, design 2026-11-13). A plain string:
    # `seniors` sits below `medical` and may not import its enum (ADR-005).
    medical_record_state: str | None = None
    # The home node's state and the room's temperature, for every role; null without a
    # node (P20, 04 §1). Set by GET /seniors only.
    home_node_state: str | None = None
    room_temperature: float | None = None


class RoomView(BaseModel):
    """The home node's latest reading (P20, 04 §1), for every role that reaches the
    senior. Plain strings: `seniors` sits below `homenode` (ADR-005). `state` is `ok` or
    `offline`; `room_state` as POST /me/room-readings answers it (P26)."""

    state: str
    temperature: float
    humidity: float | None
    reading_at: datetime
    last_motion_at: datetime | None
    room_state: str


class CaregiverView(CaregiverSummary):
    user_id: uuid.UUID  # for DELETE /seniors/{id}/caregivers/{userId}


class MedicView(BaseModel):
    """The medic who registered the senior, on the senior's page (seniors §3.3)."""

    display_name: str
    practice: str | None


class ConsentView(BaseModel):
    """The latest consent decision off the signature (04 §1, G7)."""

    decision: State
    method: State
    at: datetime


class SeniorView(SeniorDetail):
    """GET /seniors/{id} (04 §1): registration, address, medic and caregivers. One
    shape for every role (seniors SE7)."""

    call_window: str | None
    enrollment_state: State
    code: Code | None = None
    reason: str | None = None
    since: datetime | None = None
    created_at: datetime | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    # Set on every answer `senior_view` builds: GET, POST and PUT /seniors (04 §1).
    # A signature is not a decision: it only sets `signed_at`, so `consent` stays
    # null until the welcome call (G7).
    consent: ConsentView | None = None
    consent_given_at: datetime | None = None
    signed_at: datetime | None = None
    # True while one of her calls rings or is live, for the badge (UC-12). Set by
    # GET /seniors/{id} only; null on the other answers that carry the senior.
    call_in_progress: bool | None = None
    # `ok`, `not_worn` or `offline`, for her caregivers, her medic, DAS (ADR-006), and the
    # senior herself on her own page (UC-03, UC-12). Null before the first check-in.
    watch_state: WatchCondition | None = None
    # The watch's latest pulse, alongside `watch_state` (UC-03). Null before the first
    # check-in that carried one, or for callers who can't see the watch.
    last_pulse: int | None = Field(None, ge=0, le=300)
    # The home node's latest reading, for every role; null without a node (P20, 04 §1).
    # Set by GET /seniors/{id} only.
    room: RoomView | None = None
    medic: MedicView
    caregivers: list[CaregiverView]


class CheckInForm(BaseModel):
    """The watch's latest reading, relayed by the senior's phone (UC-13). `measured_at`
    carries an offset: a naive time is 422."""

    measured_at: AwareDatetime
    battery: int | None = Field(None, ge=0, le=100)
    worn: bool | None = None
    last_pulse: int | None = Field(None, ge=0, le=300)
    # Added by ADR-006; an older phone leaves them out
    resting_pulse: int | None = Field(None, ge=0, le=300)
    steps_today: int | None = Field(None, ge=0, le=100_000)
    minutes_without_steps: int | None = Field(None, ge=0)


class WatchView(BaseModel):
    """GET /seniors/{id}/watch (04 §1): the latest check-in (UC-13, ADR-006)."""

    state: WatchCondition
    last_check_in_at: datetime
    battery: int | None
    worn: bool | None
    last_pulse: int | None
    resting_pulse: int | None
    steps_today: int | None
    minutes_without_steps: int | None


class WatchReadingView(BaseModel):
    """One 5-minute bucket of GET /seniors/{id}/watch/readings (04 §1, ADR-006)."""

    at: datetime
    pulse: int | None
    battery: int | None
    worn: bool | None
    steps_today: int | None


class Citation(BaseModel):
    call_id: uuid.UUID
    quote: Annotated[str, Field(max_length=200)]


class FollowUp(BaseModel):
    topic: Annotated[str, Field(max_length=120)]
    question: Annotated[str, Field(max_length=200)]
    call_id: uuid.UUID
    quote: Annotated[str, Field(max_length=200)]


class Trend(BaseModel):
    note: Annotated[str, Field(max_length=200)]
    direction: Literal["worse", "better", "steady"]
    evidence: Annotated[list[Citation], Field(min_length=2, max_length=4)]


class SummaryContent(BaseModel):
    """What the summary agent writes, in Romanian (design §4 "What it holds")."""

    follow_ups: Annotated[list[FollowUp], Field(max_length=3)]
    how_to_talk: Annotated[
        list[Annotated[str, Field(max_length=120)]], Field(max_length=3)
    ]
    trends: Annotated[list[Trend], Field(max_length=3)]
    narrative: Annotated[str, Field(max_length=600)]


class SummaryVersionView(BaseModel):
    """GET /seniors/{id}/summary (design §5 B)."""

    content: SummaryContent
    call_id: uuid.UUID
    created_at: datetime
