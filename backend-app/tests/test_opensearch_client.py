"""Tests for OpenSearchClient (Phase 3B)."""
from unittest.mock import MagicMock, patch

import pytest


class TestOpenSearchClient:
    def test_init_creates_client_with_auth(self):
        from app.clients.opensearch_client import OpenSearchClient

        with patch("app.clients.opensearch_client.boto3") as mock_boto:
            mock_creds = MagicMock()
            mock_creds.access_key = "test-key"
            mock_creds.secret_key = "test-secret"
            mock_creds.token = "test-token"
            mock_boto.Session.return_value.get_credentials.return_value = mock_creds

            with patch("app.clients.opensearch_client.OpenSearch") as mock_os:
                client = OpenSearchClient("test-endpoint.aoss.amazonaws.com")
                mock_os.assert_called_once()

    async def test_search_knn_returns_mapped_results(self):
        from app.clients.opensearch_client import OpenSearchClient

        with patch("app.clients.opensearch_client.boto3") as mock_boto:
            mock_creds = MagicMock()
            mock_creds.access_key = "k"
            mock_creds.secret_key = "s"
            mock_creds.token = "t"
            mock_boto.Session.return_value.get_credentials.return_value = mock_creds

            with patch("app.clients.opensearch_client.OpenSearch") as mock_os:
                mock_instance = MagicMock()
                mock_instance.search.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_id": "auto-generated-id",
                                "_score": 0.92,
                                "_source": {
                                    "entity_id": "Policy#test",
                                    "node_type": "Policy",
                                    "node_label": "Test Policy",
                                    "text_content": "Content",
                                    "product_name": "Test Product",
                                },
                            }
                        ]
                    }
                }
                mock_os.return_value = mock_instance

                client = OpenSearchClient("test-endpoint")
                results = await client.search_knn([0.1] * 1024, k=5)
                assert len(results) == 1
                assert results[0]["node_id"] == "Policy#test"
                assert results[0]["score"] == 0.92

    async def test_search_text_returns_mapped_results(self):
        from app.clients.opensearch_client import OpenSearchClient

        with patch("app.clients.opensearch_client.boto3") as mock_boto:
            mock_creds = MagicMock()
            mock_creds.access_key = "k"
            mock_creds.secret_key = "s"
            mock_creds.token = "t"
            mock_boto.Session.return_value.get_credentials.return_value = mock_creds

            with patch("app.clients.opensearch_client.OpenSearch") as mock_os:
                mock_instance = MagicMock()
                mock_instance.search.return_value = {
                    "hits": {
                        "hits": [
                            {
                                "_id": "auto-id",
                                "_score": 8.5,
                                "_source": {
                                    "entity_id": "Coverage#dementia",
                                    "node_type": "Coverage",
                                    "node_label": "치매보장",
                                    "text_content": "치매 관련 보장 내용",
                                    "product_name": "H간병보험",
                                },
                            }
                        ]
                    }
                }
                mock_os.return_value = mock_instance

                client = OpenSearchClient("test-endpoint")
                results = await client.search_text("치매 관련 보장", k=10)
                assert len(results) == 1
                assert results[0]["node_id"] == "Coverage#dementia"
                assert results[0]["node_type"] == "Coverage"
                assert results[0]["product_name"] == "H간병보험"

    def test_reciprocal_rank_fusion_merges_results(self):
        from app.clients.opensearch_client import OpenSearchClient

        knn = [
            {"node_id": "A", "node_type": "Policy", "node_label": "A", "score": 0.9,
             "text_content": "", "product_name": ""},
            {"node_id": "B", "node_type": "Policy", "node_label": "B", "score": 0.8,
             "text_content": "", "product_name": ""},
        ]
        bm25 = [
            {"node_id": "C", "node_type": "Coverage", "node_label": "C", "score": 10.0,
             "text_content": "", "product_name": ""},
            {"node_id": "A", "node_type": "Policy", "node_label": "A", "score": 8.0,
             "text_content": "", "product_name": ""},
        ]
        merged = OpenSearchClient.reciprocal_rank_fusion(knn, bm25, top_k=3)
        # A appears in both lists → highest RRF score
        assert merged[0]["node_id"] == "A"
        assert len(merged) == 3

    def test_reciprocal_rank_fusion_empty_list(self):
        from app.clients.opensearch_client import OpenSearchClient

        knn = [
            {"node_id": "A", "node_type": "Policy", "node_label": "A", "score": 0.9,
             "text_content": "", "product_name": ""},
        ]
        merged = OpenSearchClient.reciprocal_rank_fusion(knn, [], top_k=5)
        assert len(merged) == 1
        assert merged[0]["node_id"] == "A"

    async def test_ping(self):
        from app.clients.opensearch_client import OpenSearchClient

        with patch("app.clients.opensearch_client.boto3") as mock_boto:
            mock_creds = MagicMock()
            mock_creds.access_key = "k"
            mock_creds.secret_key = "s"
            mock_creds.token = "t"
            mock_boto.Session.return_value.get_credentials.return_value = mock_creds

            with patch("app.clients.opensearch_client.OpenSearch") as mock_os:
                mock_instance = MagicMock()
                mock_instance.ping.return_value = True
                mock_os.return_value = mock_instance

                client = OpenSearchClient("test-endpoint")
                result = await client.ping()
                assert result is True
