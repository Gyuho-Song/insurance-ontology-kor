import logging
from contextlib import asynccontextmanager

import boto3
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, mock, mydata, personas, scenarios
from app.middleware.auth import verify_token
from app.clients.bedrock_client import BedrockClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.neptune_client import NeptuneClient
from app.clients.opensearch_client import OpenSearchClient
from app.clients.s3_client import S3Client
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.neptune = NeptuneClient(settings.neptune_endpoint, settings.neptune_port, settings.bedrock_region)
    app.state.neptune.connect()

    boto_client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    app.state.bedrock = BedrockClient(boto_client, settings.bedrock_region)

    app.state.opensearch = OpenSearchClient(
        settings.opensearch_endpoint, settings.bedrock_region
    )
    app.state.embedding = EmbeddingClient(
        boto_client, cache_size=settings.embedding_cache_size
    )

    s3_boto = boto3.client("s3", region_name=settings.bedrock_region)
    app.state.s3 = S3Client(s3_boto)

    yield

    # Shutdown
    app.state.neptune.close()


app = FastAPI(
    title="Insurance Ontology GraphRAG Engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """ALB health check endpoint (root path)."""
    return {"status": "ok"}


# Cognito JWT auth middleware — skip health checks
# FC9: AUTH_DISABLED=true (env) → 전체 우회. eval v11을 v10과 동일(무인증) 조건서 측정용. 기본은 인증 유지.
import os as _os
_AUTH_DISABLED = _os.environ.get("AUTH_DISABLED", "").lower() in ("1", "true", "yes")
_PUBLIC_PATHS = {"/", "/v1/health"}

@app.middleware("http")
async def cognito_auth_middleware(request: Request, call_next):
    if _AUTH_DISABLED or request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing authorization token"})

    token = auth_header[7:]
    try:
        claims = await verify_token(token)
        request.state.user_email = claims.get("email", "unknown")
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

    return await call_next(request)


app.include_router(chat.router)
app.include_router(personas.router)
app.include_router(scenarios.router)
app.include_router(mock.router)
app.include_router(mydata.router)
app.include_router(health.router)
