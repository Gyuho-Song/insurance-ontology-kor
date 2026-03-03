"""Tests for GET /v1/personas."""

import httpx
import pytest


@pytest.fixture
def mock_app_state(mock_neptune, mock_opensearch, mock_bedrock, mock_embedding, mock_s3):
    from app.main import app

    app.state.neptune = mock_neptune
    app.state.opensearch = mock_opensearch
    app.state.bedrock = mock_bedrock
    app.state.embedding = mock_embedding
    app.state.s3 = mock_s3
    return app


class TestPersonasEndpoint:
    async def test_get_personas_returns_200(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/personas")
            assert response.status_code == 200

    async def test_get_personas_returns_json(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/personas")
            data = response.json()
            assert "personas" in data

    async def test_personas_have_required_fields(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/personas")
            data = response.json()
            for persona in data["personas"]:
                assert "id" in persona
                assert "name" in persona
                assert "role" in persona
                assert "description" in persona
                assert "rbac_scope" in persona
                assert "avatar" in persona

    async def test_personas_contains_four_personas(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/personas")
            data = response.json()
            assert len(data["personas"]) == 4
            ids = {p["id"] for p in data["personas"]}
            assert ids == {"consultant", "customer", "underwriter", "presenter"}
