"""Tests for EmbeddingClient (Phase 3D)."""
import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest


class TestEmbeddingClient:
    def _make_bedrock_response(self, embedding: list[float]) -> dict:
        body = BytesIO(json.dumps({"embedding": embedding}).encode())
        return {"body": body}

    async def test_embed_calls_bedrock_on_cache_miss(self):
        from app.clients.embedding_client import EmbeddingClient

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = self._make_bedrock_response(
            [0.1, 0.2, 0.3]
        )

        client = EmbeddingClient(mock_bedrock, cache_size=10)
        result = await client.embed("test query")
        assert list(result) == [0.1, 0.2, 0.3]
        assert mock_bedrock.invoke_model.call_count == 1

    async def test_embed_returns_cached_on_cache_hit(self):
        from app.clients.embedding_client import EmbeddingClient

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.return_value = self._make_bedrock_response(
            [0.1, 0.2, 0.3]
        )

        client = EmbeddingClient(mock_bedrock, cache_size=10)
        result1 = await client.embed("test query")
        # Reset mock to create fresh BytesIO for potential second call
        mock_bedrock.invoke_model.return_value = self._make_bedrock_response(
            [0.4, 0.5, 0.6]
        )
        result2 = await client.embed("test query")

        # Same result (cached), only 1 invoke_model call
        assert list(result1) == list(result2)
        assert mock_bedrock.invoke_model.call_count == 1

    async def test_cache_info(self):
        from app.clients.embedding_client import EmbeddingClient

        mock_bedrock = MagicMock()
        # Return fresh BytesIO for each call (stream exhausted after read)
        mock_bedrock.invoke_model.side_effect = lambda **kwargs: self._make_bedrock_response([0.1])

        client = EmbeddingClient(mock_bedrock, cache_size=10)
        await client.embed("q1")
        await client.embed("q1")  # cache hit
        await client.embed("q2")  # cache miss

        info = client.cache_info
        assert info.hits == 1
        assert info.misses == 2

    async def test_different_queries_get_different_embeddings(self):
        from app.clients.embedding_client import EmbeddingClient

        call_count = 0

        def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            body = json.dumps({"embedding": [float(call_count)]}).encode()
            return {"body": BytesIO(body)}

        mock_bedrock = MagicMock()
        mock_bedrock.invoke_model.side_effect = side_effect

        client = EmbeddingClient(mock_bedrock, cache_size=10)
        r1 = await client.embed("query A")
        r2 = await client.embed("query B")
        assert list(r1) != list(r2)
