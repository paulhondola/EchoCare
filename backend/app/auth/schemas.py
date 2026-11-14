import uuid
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, StringConstraints, field_validator, model_validator

from app.core.phones import is_mobile, normalize


class GrantView(BaseModel):
    role: str
    senior_id: uuid.UUID | None
    # Added with the seniors work, for caregiver and senior grants (auth-layer §3.3).
    senior_form_of_address: str | None = None
    relation: str | None = None  # caregivers


class ProfileView(BaseModel):
    """GET /profile (auth-layer §3.3). Fields are only ever added: old apps read new servers."""

    display_name: str
    phone_e164: str
    grants: list[GrantView]
    # True while any campaign's warning is active, for every caller (Q5).
    warning_active: bool = False


# Staff roles (UC-14, auth-layer §3.4), folded in from staff/ (ADR-005).
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
Practice = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class StaffGrantForm(BaseModel):
    """POST /staff's body (auth-layer §3.4)."""

    display_name: Name
    phone: str
    role: Literal["das", "medic"]
    practice: Practice | None = None

    @model_validator(mode="before")
    @classmethod
    def practice_only_for_medics(cls, data: Any) -> Any:
        # Ignored for das (§3.4), so a form's empty practice field refuses nothing.
        if isinstance(data, dict) and data.get("role") != "medic":
            return {**data, "practice": None}
        return data

    @field_validator("phone")
    @classmethod
    def mobile_e164(cls, raw: str) -> str:
        e164 = normalize(raw)
        if not is_mobile(e164):
            raise ValueError("staff sign in by SMS: the number must be a mobile")
        return e164

    @model_validator(mode="after")
    def medic_has_practice(self) -> Self:
        if self.role == "medic" and self.practice is None:
            raise ValueError("a medic needs a practice")
        return self


class StaffEditForm(BaseModel):
    """PATCH /staff/{user_id}'s body (04 §2): a field left out stays as it is.

    The phone number is not editable (Q8): it is the sign-in identity.
    """

    display_name: Name | None = None
    practice: Practice | None = None


class OnDutyForm(BaseModel):
    """PUT /staff/on-duty's body (04 §2): the DAS employee who takes the hand-over."""

    user_id: uuid.UUID


class StaffMemberView(BaseModel):
    display_name: str
    phone_e164: str
    role: str
    practice: str | None


class StaffListingView(BaseModel):
    """One row of GET /staff (04 §1): a person with a das or medic grant, once."""

    id: uuid.UUID
    display_name: str
    phone_e164: str
    practice: str | None
    roles: list[str]  # das before medic, like /me's grants
    on_duty: bool
