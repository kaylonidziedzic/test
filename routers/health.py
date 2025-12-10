"""Health check endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """健康检查：返回固定 JSON，用于外部存活探测。"""
    return {"status": "healthy", "service": settings.API_TITLE}
