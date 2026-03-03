import logging
from contextlib import asynccontextmanager

import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health, mock, mydata, personas, scenarios
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


app.include_router(chat.router)
app.include_router(personas.router)
app.include_router(scenarios.router)
app.include_router(mock.router)
app.include_router(mydata.router)
app.include_router(health.router)
