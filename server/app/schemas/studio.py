from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StudioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    business_type: str = Field(min_length=1, max_length=100)


class StudioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    business_type: str | None
    owner_user_id: str | None
    created_at: datetime
    updated_at: datetime
