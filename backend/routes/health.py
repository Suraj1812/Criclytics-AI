from typing import Annotated

from fastapi import APIRouter, Depends

from backend.models.schemas import HealthResponse
from backend.services.cache_service import CacheService
from backend.services.prompt_engine import PromptEngine
from backend.services.text_engine import TextGenerationEngine
from backend.utils.config import Settings
from backend.utils.dependencies import get_cache_service, get_prompt_engine, get_settings, get_text_engine


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    settings: Annotated[Settings, Depends(get_settings)],
    cache_service: Annotated[CacheService, Depends(get_cache_service)],
    prompt_engine: Annotated[PromptEngine, Depends(get_prompt_engine)],
    text_engine: Annotated[TextGenerationEngine, Depends(get_text_engine)],
) -> HealthResponse:
    cache_status = await cache_service.ping()
    status_value = "ok" if cache_status == "up" else "degraded"
    return HealthResponse(
        status=status_value,
        cache=cache_status,
        text_engine="ready" if text_engine.ready else "ready",
        prompt_version=prompt_engine.default_version,
        environment=settings.environment,
    )
