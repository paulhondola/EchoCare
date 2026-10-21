import uuid
from datetime import datetime

from pydantic import BaseModel

from app.campaigns.models import CampaignKind, WarningLevel


class CampaignForm(BaseModel):
    """POST /campaigns' body (04 §2): the warning's kind and level; its length is fixed (Q4)."""

    kind: CampaignKind
    level: WarningLevel


class CampaignProgress(BaseModel):
    """Each senior the campaign queued, once, by their latest attempt (design 4.1)."""

    total: int
    waiting: int
    green: int
    yellow: int
    red: int
    canceled: int


class CampaignSummary(BaseModel):
    """One campaign of GET /campaigns and POST /campaigns (04 §1)."""

    id: uuid.UUID
    kind: str
    level: str
    started_by_name: str
    started_at: datetime
    warning_until: datetime
    active: bool  # warning_until > now
    progress: CampaignProgress
