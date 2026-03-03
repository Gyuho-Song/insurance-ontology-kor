"""Tests for POST /v1/mock/generate."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
def mock_pipeline_result():
    from app.core.orchestrator import PipelineResult

    return PipelineResult(
        answer_text="배당금 상계 처리 결과입니다.",
        sources=[
            {
                "node_id": "Policy#002",
                "node_type": "Policy",
                "node_label": "무배당 종신보험",
                "source_article": "제10조",
                "source_text": "배당금 상계",
            }
        ],
        traversal_events=[{"type": "expand", "node_id": "Policy#002", "hop": 1}],
        subgraph={
            "nodes": [{"id": "Policy#002", "type": "Policy", "label": "무배당 종신보험"}],
            "edges": [],
        },
        templates_used=["regulation_check"],
        topo_faithfulness=0.92,
        validation_status="completed",
    )


@pytest.fixture
def mock_app_state(mock_neptune, mock_opensearch, mock_bedrock, mock_embedding, mock_s3):
    from app.main import app

    app.state.neptune = mock_neptune
    app.state.opensearch = mock_opensearch
    app.state.bedrock = mock_bedrock
    app.state.embedding = mock_embedding
    app.state.s3 = mock_s3
    return app


class TestMockGenerateEndpoint:
    async def test_mock_generate_returns_200(
        self, mock_app_state, mock_pipeline_result, mock_s3
    ):
        with patch(
            "app.api.mock.Orchestrator.run",
            new_callable=AsyncMock,
            return_value=mock_pipeline_result,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/mock/generate",
                    json={
                        "messages": [{"role": "user", "content": "배당금 상계 처리"}],
                        "persona": "consultant",
                    },
                )
                assert response.status_code == 200

    async def test_mock_generate_caches_to_s3(
        self, mock_app_state, mock_pipeline_result, mock_s3
    ):
        with patch(
            "app.api.mock.Orchestrator.run",
            new_callable=AsyncMock,
            return_value=mock_pipeline_result,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                await client.post(
                    "/v1/mock/generate",
                    json={
                        "messages": [{"role": "user", "content": "배당금 상계 처리"}],
                        "persona": "consultant",
                    },
                )
                mock_s3.write_json.assert_called_once()
                call_args = mock_s3.write_json.call_args
                assert call_args[0][0] == "test-mock-cache"
                assert call_args[0][1].startswith("mock/consultant/")

    async def test_mock_generate_streams_data_stream_protocol(
        self, mock_app_state, mock_pipeline_result, mock_s3
    ):
        with patch(
            "app.api.mock.Orchestrator.run",
            new_callable=AsyncMock,
            return_value=mock_pipeline_result,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/mock/generate",
                    json={
                        "messages": [{"role": "user", "content": "배당금 상계"}],
                        "persona": "consultant",
                    },
                )
                lines = response.text.strip().split("\n")
                text_lines = [l for l in lines if l.startswith("0:")]
                annotation_lines = [l for l in lines if l.startswith("8:")]
                assert len(text_lines) > 0
                assert len(annotation_lines) == 1

    async def test_mock_generate_invalid_persona_returns_422(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/mock/generate",
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "persona": "admin",
                },
            )
            assert response.status_code == 422
