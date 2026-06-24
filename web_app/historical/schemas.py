from typing import Optional
from pydantic import BaseModel

class RaceResultSchema(BaseModel):
    position: Optional[int]
    classified_position: Optional[str]
    laps: Optional[int]
    time: Optional[float]
    first_name: str
    last_name: str
    team: str
    color: str

    class Config:
        from_attributes = True


class SessionSchema(BaseModel):
    id: int
    year: int
    round: int
    session_type: str
    session_type_id: int
    country: str
    circuit_name: str

    class Config:
        from_attributes = True


class StyleSchema(BaseModel):
    driver_id: int
    driver_number: int
    abbr: str
    color: str
    linestyle: str
    marker: str

    class Config:
        from_attributes = True


class LapSchema(BaseModel):
    driver_id: int
    position: Optional[int]
    lap_number: int
    track_status: int
    lap_time: float
    session_time_end: float
    is_pit_out_lap: bool
    tyre_type: int

    class Config:
        from_attributes = True