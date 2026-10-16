import uuid

from pydantic import BaseModel


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
