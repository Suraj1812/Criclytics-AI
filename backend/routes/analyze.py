import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.models.schemas import AnalyzeRequest, InsightResponse
from backend.services.analysis_service import AnalysisService
from backend.services.rate_limiter import RateLimiter
from backend.utils.dependencies import get_analysis_service, get_rate_limiter
from backend.utils.monitoring import record_metric


router = APIRouter(tags=["analysis"])


def _resolve_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = part.strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                continue
    if request.client:
        return request.client.host
    return "anonymous"


@router.post("/analyze", response_model=InsightResponse)
async def analyze_match(
    payload: AnalyzeRequest,
    request: Request,
    response: Response,
    analysis_service: Annotated[AnalysisService, Depends(get_analysis_service)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> InsightResponse:
    identifier = _resolve_client_identifier(request)
    decision = await rate_limiter.allow(identifier)
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_at)
    if not decision.allowed:
        record_metric("security.rate_limit_block", 1, {"path": "/analyze"})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for insight generation",
            headers={
                "Retry-After": str(decision.retry_after),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(decision.reset_at),
            },
        )

    result = await analysis_service.analyze(payload, client_id=identifier)
    result.request_id = getattr(request.state, "request_id", None)

    response.headers["X-Request-ID"] = result.request_id or "-"
    response.headers["X-Cache"] = "HIT" if result.cached else "MISS"
    return result
