from fastapi import Request

from backend.services.analysis_service import AnalysisService
from backend.services.cache_service import CacheService
from backend.services.prompt_engine import PromptEngine
from backend.services.rate_limiter import RateLimiter
from backend.services.text_engine import TextGenerationEngine
from backend.utils.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_cache_service(request: Request) -> CacheService:
    return request.app.state.cache_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.analysis_service


def get_prompt_engine(request: Request) -> PromptEngine:
    return request.app.state.prompt_engine


def get_text_engine(request: Request) -> TextGenerationEngine:
    return request.app.state.text_engine
