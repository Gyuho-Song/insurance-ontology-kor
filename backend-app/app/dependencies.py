from fastapi import Request

from app.clients.bedrock_client import BedrockClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.neptune_client import NeptuneClient
from app.clients.opensearch_client import OpenSearchClient
from app.clients.s3_client import S3Client
from app.core.orchestrator import Orchestrator


def get_neptune(request: Request) -> NeptuneClient:
    return request.app.state.neptune


def get_opensearch(request: Request) -> OpenSearchClient:
    return request.app.state.opensearch


def get_bedrock(request: Request) -> BedrockClient:
    return request.app.state.bedrock


def get_embedding(request: Request) -> EmbeddingClient:
    return request.app.state.embedding


def get_s3(request: Request) -> S3Client:
    return request.app.state.s3


def get_orchestrator(request: Request) -> Orchestrator:
    return Orchestrator(
        neptune=request.app.state.neptune,
        opensearch=request.app.state.opensearch,
        bedrock=request.app.state.bedrock,
        embedding=request.app.state.embedding,
    )
