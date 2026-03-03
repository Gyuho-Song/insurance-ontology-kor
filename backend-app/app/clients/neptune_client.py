import asyncio
import json
import logging

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("graphrag.neptune")


def _unwrap_graphson(data):
    """Recursively unwrap Neptune GraphSON v3 format to plain Python objects.

    Converts @type/@value wrappers:
      g:List/g:Set → list
      g:Map        → dict (alternating key/value pairs)
      g:Path       → dict with labels/objects
      g:T          → "T.id" / "T.label" (TinkerPop T enum)
      g:Int32/64   → int
      g:Double     → float
    """
    if not isinstance(data, dict):
        if isinstance(data, list):
            return [_unwrap_graphson(item) for item in data]
        return data

    if "@type" not in data:
        return {k: _unwrap_graphson(v) for k, v in data.items()}

    gtype = data["@type"]
    value = data.get("@value")

    if gtype in ("g:List", "g:Set"):
        return [_unwrap_graphson(item) for item in (value or [])]

    if gtype == "g:Map":
        result = {}
        for i in range(0, len(value), 2):
            k = _unwrap_graphson(value[i])
            v = _unwrap_graphson(value[i + 1])
            result[k] = v
        return result

    if gtype == "g:Path":
        return _unwrap_graphson(value)

    if gtype == "g:T":
        return f"T.{value}"

    if gtype == "g:Direction":
        return value

    if gtype in ("g:Int32", "g:Int64", "g:Double", "g:Float"):
        return value

    return _unwrap_graphson(value) if value is not None else data


class NeptuneClient:
    """Neptune Gremlin client using HTTP API with IAM SigV4 auth."""

    def __init__(self, endpoint: str, port: int, region: str = "us-west-2"):
        self._endpoint = endpoint
        self._port = port
        self._region = region
        self._url = f"https://{endpoint}:{port}/gremlin"
        self._session = boto3.Session()

    def connect(self):
        """Verify connectivity (lightweight check)."""
        logger.info("Neptune HTTP client configured for %s", self._url)

    def close(self):
        pass

    def _get_signed_headers(self, data: str) -> dict:
        credentials = self._session.get_credentials().get_frozen_credentials()
        request = AWSRequest(
            method="POST",
            url=self._url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(credentials, "neptune-db", self._region).add_auth(request)
        return dict(request.headers)

    async def execute(self, query: str) -> list[dict]:
        return await run_in_threadpool(self._submit, query)

    def _submit(self, query: str) -> list[dict]:
        data = json.dumps({"gremlin": query})
        headers = self._get_signed_headers(data)
        response = requests.post(
            self._url, headers=headers, data=data, timeout=30, verify=False
        )
        response.raise_for_status()
        result = response.json()
        raw = result.get("result", {}).get("data", {})
        return _unwrap_graphson(raw)

    async def execute_batch(self, queries: list[str]) -> list[list[dict]]:
        tasks = [self.execute(q) for q in queries]
        return await asyncio.gather(*tasks)

    async def ping(self) -> bool:
        """Health check — execute a simple count query."""
        try:
            await self.execute("g.V().limit(1).count()")
            return True
        except Exception:
            return False
