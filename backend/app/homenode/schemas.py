import uuid
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field

from app.homenode.models import RoomState


class RoomReadingForm(BaseModel):
    """POST /me/room-readings' body (04 §3, P21): the home node's reading, as relayed by
    the senior's phone. Times carry an offset: a naive time is 422. A temperature outside
    −10 to 50°C is accepted and used for nothing (04 §3, implausible reading)."""

    measured_at: AwareDatetime
    temperature: float
    humidity: Annotated[float, Field(ge=0, le=100)] | None = None
    last_motion_at: AwareDatetime | None = None
    # The node's prediction of the room in an hour, in °C (P26)
    forecast_60m: float | None = None


class RoomReadingView(BaseModel):
    """The room state the phone writes back to the node (P26), and whether this reading
    started a call (P21)."""

    room_state: RoomState
    queued: bool
    call_id: uuid.UUID | None
