from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routes.analyze import router as analyze_router
from backend.routes.health import router as health_router
from backend.services.analysis_service import AnalysisService
from backend.services.cache_service import CacheService
from backend.services.fallback_service import FallbackInsightService
from backend.services.predictor_engine import PredictorEngine
from backend.services.prompt_engine import PromptEngine
from backend.services.rate_limiter import RateLimiter
from backend.services.scoring_engine import ScoringEngine
from backend.services.signal_engine import SignalEngine
from backend.services.text_engine import TextGenerationEngine
from backend.services.trend_engine import TrendEngine
from backend.utils.config import Settings, get_settings
from backend.utils.errors import ApplicationError
from backend.utils.logging import clear_request_id, configure_logging, get_logger, set_request_id
from backend.utils.monitoring import record_exception, record_metric


logger = get_logger("criclytics.api")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(resolved_settings.log_level)

        cache_service = CacheService(resolved_settings)
        await cache_service.connect()

        signal_engine = SignalEngine()
        predictor_engine = PredictorEngine()
        trend_engine = TrendEngine(
            cache_service=cache_service,
            window_size=resolved_settings.trend_window_size,
            ttl_seconds=resolved_settings.trend_ttl_seconds,
        )
        scoring_engine = ScoringEngine()
        prompt_engine = PromptEngine(resolved_settings.prompt_version)
        text_engine = TextGenerationEngine(
            model_name=resolved_settings.text_engine_model,
            default_seed=resolved_settings.text_engine_seed,
        )
        fallback_service = FallbackInsightService()
        analysis_service = AnalysisService(
            settings=resolved_settings,
            cache_service=cache_service,
            signal_engine=signal_engine,
            predictor_engine=predictor_engine,
            trend_engine=trend_engine,
            scoring_engine=scoring_engine,
            prompt_engine=prompt_engine,
            text_engine=text_engine,
            fallback_service=fallback_service,
        )
        rate_limiter = RateLimiter(
            redis_client=cache_service.client,
            limit=resolved_settings.rate_limit_requests,
            window_seconds=resolved_settings.rate_limit_window_seconds,
            subnet_multiplier=resolved_settings.rate_limit_subnet_multiplier,
        )

        app.state.settings = resolved_settings
        app.state.cache_service = cache_service
        app.state.signal_engine = signal_engine
        app.state.prompt_engine = prompt_engine
        app.state.text_engine = text_engine
        app.state.analysis_service = analysis_service
        app.state.rate_limiter = rate_limiter
        app.state.predictor_engine = predictor_engine
        app.state.trend_engine = trend_engine
        app.state.scoring_engine = scoring_engine

        logger.info("Application startup complete")
        yield
        await cache_service.close()
        logger.info("Application shutdown complete")

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.prompt_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_origin_regex=resolved_settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        set_request_id(request_id)
        started_at = perf_counter()
        response = None

        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > resolved_settings.max_request_body_bytes:
                clear_request_id()
                record_metric("security.request_body_too_large", 1, {"path": request.url.path})
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds allowed size", "error_code": "payload_too_large"},
                    headers={"X-Request-ID": request_id},
                )

        try:
            response = await call_next(request)
        finally:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            record_metric(
                "http.request",
                duration_ms,
                tags={
                    "path": request.url.path,
                    "method": request.method,
                    "status": str(getattr(response, "status_code", 500)),
                },
            )
            clear_request_id()

        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
        record_metric("http.application_error", 1, {"error_code": exc.error_code, "status": str(exc.status_code)})
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "error_code": exc.error_code},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        record_metric("http.validation_error", 1, {"status": "422"})
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request payload", "error_code": "validation_error", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        record_exception("http.unhandled_error", exc, {"status": "500"})
        return JSONResponse(
            status_code=500,
            content={"detail": "Unexpected internal server error", "error_code": "internal_server_error"},
        )

    @app.get("/api", include_in_schema=False)
    async def service_root() -> dict[str, str]:
        return {
            "service": resolved_settings.app_name,
            "status": "running",
            "docs": "/docs",
            "ui": "/",
        }

    app.include_router(health_router)
    app.include_router(analyze_router)

    if frontend_dir.exists():
        # Mount the dashboard as a fallback so a single FastAPI process serves both UI and API.
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
