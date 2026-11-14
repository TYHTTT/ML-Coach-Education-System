from fastapi import APIRouter, Request

from app.schemas.health import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        dify_configured=bool(
            settings.dify_api_key.get_secret_value().strip()
            and settings.dify_api_base_url.strip()
        ),
    )
