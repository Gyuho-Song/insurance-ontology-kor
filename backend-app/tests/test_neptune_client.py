"""Tests for NeptuneClient (Phase 3A) — updated for HTTP API implementation."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestNeptuneClient:
    def test_connect_logs_url(self):
        from app.clients.neptune_client import NeptuneClient

        client = NeptuneClient("test-endpoint", 8182)
        # connect() should not raise
        client.connect()

    def test_close_is_noop(self):
        from app.clients.neptune_client import NeptuneClient

        client = NeptuneClient("test-endpoint", 8182)
        client.close()  # Should not raise

    async def test_execute_returns_results(self):
        from app.clients.neptune_client import NeptuneClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "data": [{"id": "Policy#1", "label": "Test"}]
            }
        }

        with patch("app.clients.neptune_client.requests.post", return_value=mock_response):
            with patch.object(
                NeptuneClient, "_get_signed_headers", return_value={"Authorization": "test"}
            ):
                client = NeptuneClient("test-endpoint", 8182)
                result = await client.execute("g.V().limit(1)")
                assert result == [{"id": "Policy#1", "label": "Test"}]

    async def test_execute_batch_runs_parallel(self):
        from app.clients.neptune_client import NeptuneClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": {"data": [{"id": "n1"}]}
        }

        with patch("app.clients.neptune_client.requests.post", return_value=mock_response):
            with patch.object(
                NeptuneClient, "_get_signed_headers", return_value={"Authorization": "test"}
            ):
                client = NeptuneClient("test-endpoint", 8182)
                results = await client.execute_batch(
                    ["g.V().limit(1)", "g.E().limit(1)"]
                )
                assert len(results) == 2

    async def test_ping_success(self):
        from app.clients.neptune_client import NeptuneClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": {"data": [1]}}

        with patch("app.clients.neptune_client.requests.post", return_value=mock_response):
            with patch.object(
                NeptuneClient, "_get_signed_headers", return_value={"Authorization": "test"}
            ):
                client = NeptuneClient("test-endpoint", 8182)
                assert await client.ping() is True

    async def test_ping_failure(self):
        from app.clients.neptune_client import NeptuneClient

        with patch(
            "app.clients.neptune_client.requests.post",
            side_effect=Exception("Connection refused"),
        ):
            with patch.object(
                NeptuneClient, "_get_signed_headers", return_value={"Authorization": "test"}
            ):
                client = NeptuneClient("test-endpoint", 8182)
                assert await client.ping() is False


class TestUnwrapGraphson:
    def test_unwrap_list(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {"@type": "g:List", "@value": [1, 2, 3]}
        assert _unwrap_graphson(data) == [1, 2, 3]

    def test_unwrap_map(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {"@type": "g:Map", "@value": ["key1", "val1", "key2", "val2"]}
        assert _unwrap_graphson(data) == {"key1": "val1", "key2": "val2"}

    def test_unwrap_t_id(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {"@type": "g:T", "@value": "id"}
        assert _unwrap_graphson(data) == "T.id"

    def test_unwrap_int64(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {"@type": "g:Int64", "@value": 42}
        assert _unwrap_graphson(data) == 42

    def test_unwrap_nested_path(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {
            "@type": "g:Path",
            "@value": {
                "labels": {"@type": "g:List", "@value": []},
                "objects": {
                    "@type": "g:List",
                    "@value": [
                        {
                            "@type": "g:Map",
                            "@value": [
                                {"@type": "g:T", "@value": "id"},
                                "Policy#1",
                                {"@type": "g:T", "@value": "label"},
                                "Policy",
                            ],
                        }
                    ],
                },
            },
        }
        result = _unwrap_graphson(data)
        assert result["objects"][0]["T.id"] == "Policy#1"

    def test_unwrap_plain_dict(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = {"key": "value", "num": 42}
        assert _unwrap_graphson(data) == {"key": "value", "num": 42}

    def test_unwrap_plain_list(self):
        from app.clients.neptune_client import _unwrap_graphson

        data = [1, "two", 3.0]
        assert _unwrap_graphson(data) == [1, "two", 3.0]
