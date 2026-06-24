from pydantic import BaseModel, Field
from typing import Optional

class StartEmulationRequest(BaseModel):
    session_id: int
    speed: float = Field(default=1.0, ge=1.0, le=10.0)

class EmulationStatusShema(BaseModel):
    is_running: bool
    current_session_id: Optional[int]