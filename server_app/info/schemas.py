from pydantic import BaseModel

class TyreSchema(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True


class TrackStatusSchema(BaseModel):
    id: int
    name: str
    color: str

    class Config:
        from_attributes = True