import asyncio
import json
import logging

from botocore.exceptions import ClientError
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("graphrag.bedrock")

RETRY_DELAYS = [0.1, 0.2, 0.4]
THROTTLE_CODES = ("ThrottlingException", "TooManyRequestsException")


class BedrockClient:
    """Bedrock LLM client with exponential backoff retry."""

    def __init__(self, client, region: str):
        self._client = client
        self._region = region

    async def invoke_with_retry(self, model_id: str, body: dict) -> dict:
        last_error = None
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                result = await run_in_threadpool(
                    self._client.invoke_model,
                    modelId=model_id,
                    body=json.dumps(body),
                )
                return json.loads(result["body"].read())
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code in THROTTLE_CODES:
                    last_error = e
                    logger.warning(
                        f"Bedrock throttled (attempt {attempt + 1}/{len(RETRY_DELAYS)}), "
                        f"retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
        raise last_error

    async def invoke_stream_with_retry(self, model_id: str, body: dict):
        last_error = None
        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                result = await run_in_threadpool(
                    self._client.invoke_model_with_response_stream,
                    modelId=model_id,
                    body=json.dumps(body),
                )
                return result
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code in THROTTLE_CODES:
                    last_error = e
                    await asyncio.sleep(delay)
                    continue
                raise
        raise last_error
