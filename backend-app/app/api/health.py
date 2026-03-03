import logging

from fastapi import APIRouter, Request

logger = logging.getLogger("graphrag.health")

router = APIRouter()


@router.get("/v1/health")
async def health_check(request: Request):
    """Health check for EKS readiness/liveness probes."""
    checks = {}

    # Neptune connectivity
    try:
        neptune = request.app.state.neptune
        await neptune.execute("g.V().limit(1).count()")
        checks["neptune"] = "ok"
    except Exception as e:
        logger.warning(f"Neptune health check failed: {e}")
        checks["neptune"] = "error"

    # OpenSearch connectivity
    try:
        opensearch = request.app.state.opensearch
        ok = await opensearch.ping()
        checks["opensearch"] = "ok" if ok else "error"
    except Exception as e:
        logger.warning(f"OpenSearch health check failed: {e}")
        checks["opensearch"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
