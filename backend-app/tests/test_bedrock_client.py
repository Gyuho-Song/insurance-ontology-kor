"""Tests for BedrockClient (Phase 3C)."""
import asyncio
import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError


class TestBedrockClient:
    def _make_client_error(self, code: str) -> ClientError:
        return ClientError(
            {"Error": {"Code": code, "Message": "test"}}, "InvokeModel"
        )

    async def test_invoke_with_retry_success_first_attempt(self):
        from app.clients.bedrock_client import BedrockClient

        mock_boto = MagicMock()
        body_stream = BytesIO(json.dumps({"content": [{"text": "ok"}]}).encode())
        mock_boto.invoke_model.return_value = {"body": body_stream}

        client = BedrockClient(mock_boto, "us-west-2")
        result = await client.invoke_with_retry("test-model", {"messages": []})
        assert result["content"][0]["text"] == "ok"

    async def test_invoke_with_retry_throttle_then_success(self):
        from app.clients.bedrock_client import BedrockClient

        mock_boto = MagicMock()
        body_stream = BytesIO(json.dumps({"content": [{"text": "ok"}]}).encode())
        mock_boto.invoke_model.side_effect = [
            self._make_client_error("ThrottlingException"),
            {"body": body_stream},
        ]

        client = BedrockClient(mock_boto, "us-west-2")
        result = await client.invoke_with_retry("test-model", {"messages": []})
        assert result["content"][0]["text"] == "ok"
        assert mock_boto.invoke_model.call_count == 2

    async def test_invoke_with_retry_max_retries_exceeded(self):
        from app.clients.bedrock_client import BedrockClient

        mock_boto = MagicMock()
        mock_boto.invoke_model.side_effect = self._make_client_error(
            "ThrottlingException"
        )

        client = BedrockClient(mock_boto, "us-west-2")
        with pytest.raises(ClientError):
            await client.invoke_with_retry("test-model", {"messages": []})
        assert mock_boto.invoke_model.call_count == 3

    async def test_invoke_with_retry_non_throttle_error_raises_immediately(self):
        from app.clients.bedrock_client import BedrockClient

        mock_boto = MagicMock()
        mock_boto.invoke_model.side_effect = self._make_client_error(
            "ValidationException"
        )

        client = BedrockClient(mock_boto, "us-west-2")
        with pytest.raises(ClientError):
            await client.invoke_with_retry("test-model", {"messages": []})
        assert mock_boto.invoke_model.call_count == 1

    async def test_invoke_stream_with_retry_success(self):
        from app.clients.bedrock_client import BedrockClient

        mock_boto = MagicMock()
        mock_boto.invoke_model_with_response_stream.return_value = {
            "body": [{"chunk": {"bytes": b'{"type":"content_block_delta"}'}}]
        }

        client = BedrockClient(mock_boto, "us-west-2")
        result = await client.invoke_stream_with_retry("test-model", {"messages": []})
        assert "body" in result
