import asyncio
from typing import Literal

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.db import session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["setu-agent"]
    db: Literal["ok", "unavailable"]
    version: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    try:
        db_ok = await asyncio.wait_for(
            run_in_threadpool(session.ping), timeout=settings.db_check_timeout_seconds + 1
        )
    except TimeoutError:
        db_ok = False
    return HealthResponse(
        status="ok",
        service="setu-agent",
        db="ok" if db_ok else "unavailable",
        version=settings.app_version,
    )
