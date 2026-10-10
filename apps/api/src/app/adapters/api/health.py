import os

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """status plus deploy fingerprint so the browser console shows which Mac build is live."""
    return {
        "status": "ok",
        "build": os.environ.get("BUILD_SHA", "dev"),
        "source": os.environ.get("BUILD_SOURCE", "local-mac"),
    }
