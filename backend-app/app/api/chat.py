import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.clients.s3_client import S3Client
from app.config import settings
from app.core.orchestrator import Orchestrator
from app.dependencies import get_orchestrator, get_s3
from app.models.response import ChatRequest

logger = logging.getLogger("graphrag.chat")

router = APIRouter()


@router.post("/v1/chat")
async def chat_stream(
    request: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    s3: S3Client = Depends(get_s3),
):
    if request.mock_mode:
        return await _mock_replay(request, s3, orchestrator)

    async def generate():
        async for event_type, data in orchestrator.run_stream(request):
            if event_type == "text":
                yield f'0:{json.dumps(data, ensure_ascii=False)}\n'
            elif event_type == "data":
                yield f'2:{json.dumps([data], ensure_ascii=False)}\n'
            elif event_type == "annotation":
                yield f"8:[{json.dumps(data, ensure_ascii=False)}]\n"

    return StreamingResponse(generate(), media_type="text/plain")


async def _mock_replay(
    request: ChatRequest,
    s3: S3Client,
    orchestrator: Orchestrator,
):
    """Try to replay from S3 mock cache. Falls back to live if cache miss."""
    query = request.messages[-1]["content"]
    cache_key = f"mock/{request.persona}/{query[:80]}.json"

    cached = await s3.read_json(settings.mock_cache_bucket, cache_key)

    if cached is None:
        logger.warning(f"Mock cache miss for key={cache_key}, falling back to live")

        async def generate_live():
            async for event_type, data in orchestrator.run_stream(request):
                if event_type == "text":
                    yield f'0:{json.dumps(data, ensure_ascii=False)}\n'
                elif event_type == "data":
                    yield f'2:{json.dumps([data], ensure_ascii=False)}\n'
                elif event_type == "annotation":
                    data["isMockResponse"] = False
                    yield f"8:[{json.dumps(data, ensure_ascii=False)}]\n"

        return StreamingResponse(generate_live(), media_type="text/plain")

    logger.info(f"Mock cache hit for key={cache_key}")

    async def generate_cached():
        text = cached["answer_text"]
        chunk_size = 40
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            yield f'0:{json.dumps(chunk, ensure_ascii=False)}\n'

        annotation = {
            "intent": cached.get("intent"),
            "confidence": cached.get("confidence"),
            "sources": cached.get("sources", []),
            "traversalEvents": cached.get("traversal_events", []),
            "subgraph": cached.get("subgraph", {"nodes": [], "edges": []}),
            "topoFaithfulness": cached.get("topo_faithfulness"),
            "templatesUsed": cached.get("templates_used", []),
            "validationStatus": cached.get("validation_status", "completed"),
            "isMockResponse": True,
        }
        yield f"8:[{json.dumps(annotation, ensure_ascii=False)}]\n"

    return StreamingResponse(generate_cached(), media_type="text/plain")
