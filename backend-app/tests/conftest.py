import os
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

# Set test environment variables before importing settings
os.environ.setdefault("NEPTUNE_ENDPOINT", "test-neptune.cluster.us-west-2.neptune.amazonaws.com")
os.environ.setdefault("OPENSEARCH_ENDPOINT", "test-opensearch.us-west-2.aoss.amazonaws.com")
os.environ.setdefault("MOCK_CACHE_BUCKET", "test-mock-cache")
os.environ.setdefault("PARSED_BUCKET", "test-parsed-data")


# --- Mock Clients ---


@pytest.fixture
def mock_neptune():
    client = AsyncMock()
    client.execute.return_value = [{"id": "Policy#test", "label": "Test Policy"}]
    client.execute_batch.return_value = [[{"id": "Policy#test"}]]
    return client


@pytest.fixture
def mock_opensearch():
    client = AsyncMock()
    client.search_knn.return_value = [
        {
            "node_id": "Policy#test",
            "node_type": "Policy",
            "node_label": "Test Policy",
            "score": 0.92,
            "text_content": "Test content",
        }
    ]
    client.search_text.return_value = []
    client.ping.return_value = True
    return client


@pytest.fixture
def mock_bedrock():
    client = AsyncMock()
    client.invoke_with_retry.return_value = {
        "content": [{"text": '["claim1", "claim2"]'}]
    }
    return client


@pytest.fixture
def mock_embedding():
    client = AsyncMock()
    client.embed.return_value = [0.1] * 1024
    return client


@pytest.fixture
def mock_s3():
    client = AsyncMock()
    client.read_json.return_value = {"scenario_id": "A", "query": "test"}
    client.write_json.return_value = None
    return client


# --- httpx.AsyncClient for streaming endpoint tests ---


@pytest.fixture
async def async_client():
    """httpx.AsyncClient for testing StreamingResponse endpoints chunk-by-chunk."""
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# --- Settings override ---


@pytest.fixture
def test_settings():
    from app.config import Settings

    return Settings(
        neptune_endpoint="test-neptune",
        opensearch_endpoint="test-opensearch",
        mock_cache_bucket="test-mock-cache",
        parsed_bucket="test-parsed-data",
    )
