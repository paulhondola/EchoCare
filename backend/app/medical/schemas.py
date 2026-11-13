from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.medical.models import MedicalRecordState


class MedicalItem(BaseModel):
    """One condition with the question to ask about it (design §4)."""

    condition: str = Field(max_length=120)
    question: str = Field(max_length=200)
    worrying: str = Field(max_length=200)
    evidence: str = Field(max_length=300)
    included: bool = True


class MedicalProfile(BaseModel):
    """The analyzer's output."""

    items: list[MedicalItem] = Field(max_length=6)


class MedicalRecordView(BaseModel):
    state: MedicalRecordState
    uploaded_at: datetime
    analyzed_at: datetime | None
    confirmed_at: datetime | None
    items: list[MedicalItem] | None
    pdf_url: str | None


Text200 = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class ConfirmItem(BaseModel):
    included: bool
    question: Text200
    # The reply that would worry, rewritten with an edited question; None keeps it.
    worrying: Text200 | None = None


class MedicalConfirmForm(BaseModel):
    items: list[ConfirmItem]
    # The `analyzed_at` of the profile the medic reviewed; a newer one is refused.
    analyzed_at: datetime | None = None
