from typing import Literal

from pydantic import BaseModel


class ServiceHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "label-guardian-backend"
    environment: str
    version: str
