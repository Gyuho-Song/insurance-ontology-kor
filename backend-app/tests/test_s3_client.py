"""Tests for S3Client (Phase 3E)."""
import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest


class TestS3Client:
    async def test_read_json(self):
        from app.clients.s3_client import S3Client

        mock_boto = MagicMock()
        data = {"scenario_id": "A", "query": "test"}
        mock_boto.get_object.return_value = {
            "Body": BytesIO(json.dumps(data).encode())
        }

        client = S3Client(mock_boto)
        result = await client.read_json("test-bucket", "test-key.json")
        assert result["scenario_id"] == "A"

    async def test_write_json(self):
        from app.clients.s3_client import S3Client

        mock_boto = MagicMock()
        client = S3Client(mock_boto)

        data = {"scenario_id": "A"}
        await client.write_json("test-bucket", "test-key.json", data)
        mock_boto.put_object.assert_called_once()
        call_kwargs = mock_boto.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "test-key.json"

    async def test_read_json_not_found(self):
        from app.clients.s3_client import S3Client
        from botocore.exceptions import ClientError

        mock_boto = MagicMock()
        mock_boto.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
        )

        client = S3Client(mock_boto)
        result = await client.read_json("test-bucket", "missing.json")
        assert result is None
