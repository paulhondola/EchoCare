import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role
from app.auth.service import Caller, require_roles
from app.campaigns.schemas import CampaignForm, CampaignSummary
from app.campaigns.service import (
    campaign_summaries,
    cancel_lapsed,
    end_campaign,
    start_campaign,
)
from app.core.db import get_session

router = APIRouter()


@router.post(
    "/campaigns",
    status_code=201,
    responses={
        200: {
            "model": CampaignSummary,
            "description": "The running campaign of that kind and level (Q3)",
        }
    },
)
async def launch_campaign(
    body: CampaignForm,
    response: Response,
    caller: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CampaignSummary:
    """Starts a campaign of one kind and level: 201, with one queued call per active
    senior (04 §2). While one of that kind and level has an active warning, answers it
    with 200 and creates nothing (Q3)."""
    summary, created = await start_campaign(session, caller, body)
    if not created:
        response.status_code = 200
    return summary


@router.get("/campaigns")
async def list_campaigns(
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CampaignSummary]:
    """Campaigns, newest first, with their progress, for the dashboard's 'Campanii' (04 §1, Q2)."""
    await cancel_lapsed(session)
    await session.commit()
    return await campaign_summaries(session)


@router.post("/campaigns/{campaign_id}/end")
async def finish_campaign(
    campaign_id: uuid.UUID,
    _: Annotated[Caller, Depends(require_roles(Role.das))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CampaignSummary:
    """Ends a campaign's warning now and cancels its queued calls; the codes stay (Q9).
    A repeat answers the same; no such campaign is 404 `not_found`."""
    return await end_campaign(session, campaign_id)
