from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness check")
def health():
    return {"status": "ok"}
