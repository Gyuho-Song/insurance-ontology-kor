import logging

import boto3
from fastapi.concurrency import run_in_threadpool
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

logger = logging.getLogger("graphrag.opensearch")


class OpenSearchClient:
    """OpenSearch Serverless k-NN client with IAM SigV4 auth."""

    def __init__(self, endpoint: str, region: str = "us-west-2"):
        # Strip protocol prefix if present (ConfigMap may include https://)
        host = endpoint.replace("https://", "").replace("http://", "").rstrip("/")
        session = boto3.Session()
        self._auth = AWSV4SignerAuth(session.get_credentials(), region, "aoss")
        self._client = OpenSearch(
            hosts=[{"host": host, "port": 443}],
            http_auth=self._auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        self._index = "ontology-vectors"

    async def search_knn(
        self, query_vector: list[float], k: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        # nmslib doesn't support knn-level filters. Use post-filter instead:
        # over-fetch k*4 results, then filter client-side by document_id.
        fetch_k = k * 4 if document_ids else k
        body = {
            "size": fetch_k,
            "query": {"knn": {"embedding": {"vector": query_vector, "k": fetch_k}}},
            "_source": ["entity_id", "node_type", "node_label", "text_content",
                         "product_name", "document_id"],
        }
        result = await run_in_threadpool(
            self._client.search, index=self._index, body=body
        )
        hits = [
            {
                "node_id": hit["_source"].get("entity_id", hit["_id"]),
                "node_type": hit["_source"]["node_type"],
                "node_label": hit["_source"]["node_label"],
                "score": hit["_score"],
                "text_content": hit["_source"].get("text_content", ""),
                "product_name": hit["_source"].get("product_name", ""),
                "document_id": hit["_source"].get("document_id", ""),
            }
            for hit in result["hits"]["hits"]
        ]
        if document_ids:
            doc_id_set = set(document_ids)
            hits = [h for h in hits if h.get("document_id") in doc_id_set][:k]
        else:
            hits = hits[:k]
        return hits

    async def search_by_product_name(
        self, product_name: str, node_type: str | None = "Policy", k: int = 3
    ) -> list[dict]:
        """Search for nodes matching a product name via phrase-prefix on node_label.

        Uses ``match_phrase_prefix`` so that partial names like "H보장보험"
        match indexed labels such as "한화생명 H보장보험1 무배당".
        When node_type is None, searches across all node types.
        """
        bool_query: dict = {
            "should": [
                {"match_phrase_prefix": {"node_label": {"query": product_name, "boost": 3}}},
                {"match": {"text_content": product_name}},
            ],
            "minimum_should_match": 1,
        }
        if node_type is not None:
            bool_query["filter"] = [{"term": {"node_type": node_type}}]
        body = {
            "size": k,
            "query": {"bool": bool_query},
            "_source": ["entity_id", "node_type", "node_label", "text_content", "product_name"],
        }
        result = await run_in_threadpool(
            self._client.search, index=self._index, body=body
        )
        return [
            {
                "node_id": hit["_source"].get("entity_id", hit["_id"]),
                "node_type": hit["_source"]["node_type"],
                "node_label": hit["_source"]["node_label"],
                "score": hit["_score"],
                "text_content": hit["_source"].get("text_content", ""),
                "product_name": hit["_source"].get("product_name", ""),
            }
            for hit in result["hits"]["hits"]
        ]

    async def resolve_product_policy(
        self, product_name: str, k: int = 1,
    ) -> list[dict]:
        """Resolve a product name to Policy nodes using exact substring matching.

        Uses the ``node_label.raw`` keyword field for precise wildcard matching,
        avoiding Nori tokenizer ambiguity (e.g. "시그니처H암보험" won't confuse
        with "시그니처H통합건강보험").  Falls back to match_phrase_prefix if
        the wildcard yields no results.

        When multiple matches exist (e.g. "H종신보험" matches both "H종신보험"
        and "상속H종신보험"), the shortest label wins (closest to user's query).
        """
        _source = ["entity_id", "node_type", "node_label", "text_content",
                    "product_name", "document_id"]

        # Strategy 1: Exact substring via keyword wildcard (most precise)
        body = {
            "size": k * 5,  # over-fetch for client-side re-ranking
            "query": {"bool": {
                "must": [{"wildcard": {"node_label.raw": {"value": f"*{product_name}*"}}}],
                "filter": [{"term": {"node_type": "Policy"}}],
            }},
            "_source": _source,
        }
        result = await run_in_threadpool(
            self._client.search, index=self._index, body=body
        )
        hits = result["hits"]["hits"]

        # Strategy 2: Fallback to phrase_prefix (handles partial/variant names)
        if not hits:
            body = {
                "size": k * 5,
                "query": {"bool": {
                    "must": [{"match_phrase_prefix": {"node_label": {"query": product_name}}}],
                    "filter": [{"term": {"node_type": "Policy"}}],
                }},
                "_source": _source,
            }
            result = await run_in_threadpool(
                self._client.search, index=self._index, body=body
            )
            hits = result["hits"]["hits"]

        # Re-rank: prefer shortest label (closest match to user query)
        hits.sort(key=lambda h: len(h["_source"].get("node_label", "")))

        return [
            {
                "node_id": hit["_source"].get("entity_id", hit["_id"]),
                "node_type": hit["_source"]["node_type"],
                "node_label": hit["_source"]["node_label"],
                "score": hit["_score"],
                "text_content": hit["_source"].get("text_content", ""),
                "product_name": hit["_source"].get("product_name", ""),
                "document_id": hit["_source"].get("document_id", ""),
            }
            for hit in hits[:k]
        ]

    async def search_text(
        self, query_text: str, k: int = 50,
        node_types: list[str] | None = None,
    ) -> list[dict]:
        """BM25 text search on text_content and node_label fields.

        Complements k-NN vector search for topic-based queries where
        keyword matching outperforms semantic similarity (e.g. "치매 관련 보장"
        should match documents containing "치매" literally).
        """
        must: list[dict] = [
            {"multi_match": {
                "query": query_text,
                "fields": ["text_content", "node_label^2"],
                "type": "best_fields",
            }},
        ]
        if node_types:
            must.append({"terms": {"node_type": node_types}})
        body = {
            "size": k,
            "query": {"bool": {"must": must}},
            "_source": ["entity_id", "node_type", "node_label", "text_content", "product_name", "document_id"],
        }
        result = await run_in_threadpool(
            self._client.search, index=self._index, body=body
        )
        return [
            {
                "node_id": hit["_source"].get("entity_id", hit["_id"]),
                "node_type": hit["_source"]["node_type"],
                "node_label": hit["_source"]["node_label"],
                "score": hit["_score"],
                "text_content": hit["_source"].get("text_content", ""),
                "product_name": hit["_source"].get("product_name", ""),
                "document_id": hit["_source"].get("document_id", ""),
            }
            for hit in result["hits"]["hits"]
        ]

    @staticmethod
    def reciprocal_rank_fusion(
        *result_lists: list[dict],
        k_rrf: int = 60,
        top_k: int = 5,
    ) -> list[dict]:
        """Merge multiple ranked result lists using Reciprocal Rank Fusion.

        RRF score for each document = sum(1 / (k_rrf + rank_i + 1))
        across all result lists where it appears.
        Documents ranked highly in BOTH lists get the strongest boost.
        """
        scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}
        for results in result_lists:
            for rank, doc in enumerate(results):
                nid = doc["node_id"]
                scores[nid] = scores.get(nid, 0.0) + 1.0 / (k_rrf + rank + 1)
                if nid not in doc_map:
                    doc_map[nid] = doc
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        merged = []
        for nid, rrf_score in ranked[:top_k]:
            entry = dict(doc_map[nid])
            entry["score"] = rrf_score
            merged.append(entry)
        return merged

    async def ping(self) -> bool:
        """Health check using _cat/indices (AOSS returns 404 on root /)."""
        try:
            await run_in_threadpool(self._client.cat.indices)
            return True
        except Exception:
            return False
