"""Tests for GET /v1/scenarios."""

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


class TestScenariosEndpoint:
    async def test_get_scenarios_returns_200(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/scenarios")
            assert response.status_code == 200

    async def test_get_scenarios_returns_json(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/scenarios")
            data = response.json()
            assert "scenarios" in data

    async def test_scenarios_have_required_fields(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/scenarios")
            data = response.json()
            for scenario in data["scenarios"]:
                assert "id" in scenario
                assert "title" in scenario
                assert "description" in scenario
                assert "query" in scenario
                assert "personas" in scenario
                assert "category" in scenario

    async def test_scenarios_contains_five_scenarios(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/scenarios")
            data = response.json()
            assert len(data["scenarios"]) == 8
            ids = {s["id"] for s in data["scenarios"]}
            assert ids == {"A", "B", "C", "D", "E", "F", "G", "H"}
