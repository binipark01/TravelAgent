from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "Travel Agent API. Use /health or open the React frontend.",
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
