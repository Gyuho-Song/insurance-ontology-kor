"""Tests for GET /v1/health."""

import httpx
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_app_state(mock_neptune, mock_opensearch, mock_bedrock, mock_embedding, mock_s3):
    from app.main import app

    app.state.neptune = mock_neptune
    app.state.opensearch = mock_opensearch
    app.state.bedrock = mock_bedrock
    app.state.embedding = mock_embedding
    app.state.s3 = mock_s3
    return app


class TestHealthEndpoint:
    async def test_health_returns_200(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/health")
            assert response.status_code == 200

    async def test_health_healthy_when_all_ok(self, mock_app_state, mock_neptune, mock_opensearch):
        mock_neptune.execute.return_value = [{"count": 1}]
        mock_opensearch.ping.return_value = True
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/health")
            data = response.json()
            assert data["status"] == "healthy"
            assert data["checks"]["neptune"] == "ok"
            assert data["checks"]["opensearch"] == "ok"

    async def test_health_degraded_when_neptune_fails(
        self, mock_app_state, mock_neptune, mock_opensearch
    ):
        mock_neptune.execute.side_effect = Exception("connection refused")
        mock_opensearch.ping.return_value = True
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/health")
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["neptune"] == "error"
            assert data["checks"]["opensearch"] == "ok"

    async def test_health_degraded_when_opensearch_fails(
        self, mock_app_state, mock_neptune, mock_opensearch
    ):
        mock_neptune.execute.return_value = [{"count": 1}]
        mock_opensearch.ping.side_effect = Exception("timeout")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/health")
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["neptune"] == "ok"
            assert data["checks"]["opensearch"] == "error"

    async def test_health_degraded_when_all_fail(
        self, mock_app_state, mock_neptune, mock_opensearch
    ):
        mock_neptune.execute.side_effect = Exception("down")
        mock_opensearch.ping.side_effect = Exception("down")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/health")
            data = response.json()
            assert data["status"] == "degraded"
            assert data["checks"]["neptune"] == "error"
            assert data["checks"]["opensearch"] == "error"
