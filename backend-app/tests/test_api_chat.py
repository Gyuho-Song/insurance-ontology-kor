"""Tests for POST /v1/chat — streaming endpoint with httpx.AsyncClient."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
def mock_stream_events():
    """Return a list of (event_type, data) tuples that run_stream would yield."""
    annotation = {
        "sources": [
            {
                "node_id": "Policy#001",
                "node_type": "Policy",
                "node_label": "종신보험",
                "source_article": "제5조",
                "source_text": "사망보험금 지급",
            }
        ],
        "traversalEvents": [
            {"type": "expand", "node_id": "Policy#001", "hop": 1}
        ],
        "subgraph": {
            "nodes": [
                {"id": "Policy#001", "type": "Policy", "label": "종신보험"}
            ],
            "edges": [],
        },
        "topoFaithfulness": 0.95,
        "templatesUsed": ["coverage_lookup"],
        "validationStatus": "completed",
    }
    return [
        ("text", "보험금 지급 조건은 "),
        ("text", "사망, 장해, 진단 시 지급됩니다."),
        ("annotation", annotation),
    ]


@pytest.fixture
def mock_app_state(
    mock_neptune, mock_opensearch, mock_bedrock, mock_embedding, mock_s3
):
    """Patch app.state with mock clients so lifespan doesn't run."""
    from app.main import app

    app.state.neptune = mock_neptune
    app.state.opensearch = mock_opensearch
    app.state.bedrock = mock_bedrock
    app.state.embedding = mock_embedding
    app.state.s3 = mock_s3
    return app


def _mock_run_stream(events):
    """Create an async generator from a list of events."""

    async def mock_run_stream(self, request):
        for event in events:
            yield event

    return mock_run_stream


class TestChatEndpoint:
    """POST /v1/chat streaming tests using httpx.AsyncClient."""

    async def test_chat_returns_200_streaming(
        self, mock_app_state, mock_stream_events
    ):
        with patch.object(
            type(mock_app_state.state).__dict__.get("orchestrator", None).__class__
            if False
            else None,
            "run_stream",
            side_effect=None,
        ) if False else patch(
            "app.core.orchestrator.Orchestrator.run_stream",
            _mock_run_stream(mock_stream_events),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "보험금 조건"}
                        ],
                        "persona": "consultant",
                    },
                )
                assert response.status_code == 200
                assert (
                    response.headers["content-type"]
                    == "text/plain; charset=utf-8"
                )

    async def test_chat_stream_data_stream_protocol(
        self, mock_app_state, mock_stream_events
    ):
        """Verify chunks follow Vercel AI SDK Data Stream Protocol."""
        with patch(
            "app.core.orchestrator.Orchestrator.run_stream",
            _mock_run_stream(mock_stream_events),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "보험금 조건"}
                        ],
                        "persona": "consultant",
                    },
                )
                lines = response.text.strip().split("\n")
                text_lines = [line for line in lines if line.startswith("0:")]
                assert len(text_lines) > 0
                annotation_lines = [
                    line for line in lines if line.startswith("8:")
                ]
                assert len(annotation_lines) == 1

    async def test_chat_annotation_contains_required_fields(
        self, mock_app_state, mock_stream_events
    ):
        """Annotation (8:) must include sources, traversalEvents, subgraph, etc."""
        with patch(
            "app.core.orchestrator.Orchestrator.run_stream",
            _mock_run_stream(mock_stream_events),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "보험금 조건"}
                        ],
                        "persona": "consultant",
                    },
                )
                lines = response.text.strip().split("\n")
                annotation_line = [
                    line for line in lines if line.startswith("8:")
                ][0]
                payload = json.loads(annotation_line[2:])
                annotation = payload[0]
                assert "sources" in annotation
                assert "traversalEvents" in annotation
                assert "subgraph" in annotation
                assert "topoFaithfulness" in annotation
                assert "templatesUsed" in annotation
                assert "validationStatus" in annotation

    async def test_chat_text_chunks_reassemble(
        self, mock_app_state, mock_stream_events
    ):
        """Text chunks (0:) should reassemble to the full answer."""
        with patch(
            "app.core.orchestrator.Orchestrator.run_stream",
            _mock_run_stream(mock_stream_events),
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=mock_app_state),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/v1/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "보험금 조건"}
                        ],
                        "persona": "consultant",
                    },
                )
                lines = response.text.strip().split("\n")
                text_lines = [
                    line for line in lines if line.startswith("0:")
                ]
                reassembled = ""
                for tl in text_lines:
                    chunk_str = json.loads(tl[2:])
                    reassembled += chunk_str
                expected = "보험금 지급 조건은 사망, 장해, 진단 시 지급됩니다."
                assert reassembled == expected

    async def test_chat_invalid_persona_returns_422(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/chat",
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "persona": "hacker",
                },
            )
            assert response.status_code == 422

    async def test_chat_empty_messages_returns_422(self, mock_app_state):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=mock_app_state),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/chat",
                json={
                    "messages": [],
                    "persona": "consultant",
                },
            )
            assert response.status_code == 422
