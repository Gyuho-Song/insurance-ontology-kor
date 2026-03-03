import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.clients.s3_client import S3Client
from app.config import settings
from app.core.orchestrator import Orchestrator
from app.dependencies import get_orchestrator, get_s3
from app.models.response import ChatRequest

logger = logging.getLogger("graphrag.mock")

router = APIRouter()


@router.post("/v1/mock/generate")
async def mock_generate(
    request: ChatRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    s3: S3Client = Depends(get_s3),
):
    """Generate a response and cache it to S3 for mock mode replay."""
    pipeline_result = await orchestrator.run(request)

    cache_key = f"mock/{request.persona}/{request.messages[-1]['content'][:80]}.json"
    cache_data = {
        "answer_text": pipeline_result.answer_text,
        "intent": pipeline_result.intent,
        "confidence": pipeline_result.confidence,
        "sources": pipeline_result.sources,
        "traversal_events": pipeline_result.traversal_events,
        "subgraph": pipeline_result.subgraph,
        "templates_used": pipeline_result.templates_used,
        "topo_faithfulness": pipeline_result.topo_faithfulness,
        "validation_status": pipeline_result.validation_status,
    }
    await s3.write_json(settings.mock_cache_bucket, cache_key, cache_data)

    async def generate():
        text = pipeline_result.answer_text
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            yield f'0:{json.dumps(chunk, ensure_ascii=False)}\n'

        annotation = {
            "intent": pipeline_result.intent,
            "confidence": pipeline_result.confidence,
            "sources": pipeline_result.sources,
            "traversalEvents": pipeline_result.traversal_events,
            "subgraph": pipeline_result.subgraph,
            "topoFaithfulness": pipeline_result.topo_faithfulness,
            "templatesUsed": pipeline_result.templates_used,
            "validationStatus": pipeline_result.validation_status,
        }
        yield f"8:[{json.dumps(annotation, ensure_ascii=False)}]\n"

    return StreamingResponse(generate(), media_type="text/plain")
