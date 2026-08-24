from typing import Literal

from pydantic import BaseModel, Field


class ServiceHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "label-guardian-backend"
    environment: str
    version: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
    analysis: str = Field(default="", description="Phân tích nội bộ")
