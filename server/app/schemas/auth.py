from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TrialRequestCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)


class AccountRead(BaseModel):
    id: str
    username: str
    role: Literal["customer", "owner"] = "customer"


class TrialRead(BaseModel):
    order_no: str
    user_id: str
    username: str
    plan_id: Literal["FREE"] = "FREE"
    plan_name: str = "免费体验"
    amount_cents: int = 0
    payment_status: Literal["not_required"] = "not_required"
    status: Literal["pending"] = "pending"
    created_at: datetime
