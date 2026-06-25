from pydantic import BaseModel
from datetime import datetime


class RealTimePositionSchema(BaseModel):
    driver_number: int
    abbr: str
    color: str
    time_utc: datetime
    status: str
    x: int
    y: int
    z: int

    class Config:
        from_attributes = True


class TrackCornerSchema(BaseModel):
    x: float
    y: float
    angle: float
    number: int 
    distance: float
    rotation: int

    class Config:
        from_attributes = True


class TrackMapSchema(BaseModel):
    x: float
    y: float

    class Config:
        from_attributes = True


class RealTimeMessageSchema(BaseModel):
    time_utc: datetime
    lap: int
    message: str

    class Config:
        from_attributes = True


class LiveTimestampSchema(BaseModel):
    time: datetime

    class Config:
        from_attributes = True


class RealTimeLapsSchema(BaseModel):
    driver_number: int
    lap_time: float
    lap_number: int
    stint_number: int
    tyre_type: int
    tyre_age: int
    end_time_utc: datetime
    is_predicted_future: bool

    class Config:
        from_attributes = True