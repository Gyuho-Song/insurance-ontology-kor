import json
import logging

from botocore.exceptions import ClientError
from fastapi.concurrency import run_in_threadpool

logger = logging.getLogger("graphrag.s3")


class S3Client:
    """S3 read/write for mock cache JSON."""

    def __init__(self, client):
        self._client = client

    async def read_json(self, bucket: str, key: str) -> dict | None:
        try:
            result = await run_in_threadpool(
                self._client.get_object, Bucket=bucket, Key=key
            )
            body = result["Body"].read()
            return json.loads(body)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"S3 key not found: s3://{bucket}/{key}")
                return None
            raise

    async def write_json(self, bucket: str, key: str, data: dict) -> None:
        await run_in_threadpool(
            self._client.put_object,
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
