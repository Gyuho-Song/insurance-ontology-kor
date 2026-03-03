import json
import logging
from functools import lru_cache

from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("graphrag.embedding")


class EmbeddingClient:
    """Bedrock Titan embedding with LRU cache."""

    def __init__(self, bedrock_client, cache_size: int = 256):
        self._bedrock = bedrock_client
        self._embed_cached = lru_cache(maxsize=cache_size)(self._embed_sync)

    async def embed(self, text: str) -> list[float]:
        result = await run_in_threadpool(self._embed_cached, text)
        return list(result)

    def _embed_sync(self, text: str) -> tuple[float, ...]:
        response = self._bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text}),
        )
        embedding = json.loads(response["body"].read())["embedding"]
        return tuple(embedding)

    @property
    def cache_info(self):
        return self._embed_cached.cache_info()
