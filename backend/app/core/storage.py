"""Async S3/MinIO wrapper using boto3 + asyncio.to_thread."""

import asyncio
import uuid
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class S3Storage:
    def __init__(self) -> None:
        self._s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )

    async def ensure_bucket(self, bucket: str) -> None:
        def _create() -> None:
            try:
                self._s3.head_bucket(Bucket=bucket)
            except ClientError:
                self._s3.create_bucket(Bucket=bucket)

        await asyncio.to_thread(_create)

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        kwargs: dict = {"Bucket": bucket, "Key": key, "Body": data, "ContentType": content_type}
        if metadata:
            kwargs["Metadata"] = metadata
        await asyncio.to_thread(self._s3.put_object, **kwargs)

    async def get_presigned_url(
        self, bucket: str, key: str, expires: int = 3600, filename: str | None = None
    ) -> str:
        params: dict = {"Bucket": bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        url: str = await asyncio.to_thread(
            self._s3.generate_presigned_url,
            "get_object",
            Params=params,
            ExpiresIn=expires,
        )
        return url

    async def delete(self, bucket: str, key: str) -> None:
        await asyncio.to_thread(self._s3.delete_object, Bucket=bucket, Key=key)

    @staticmethod
    def make_key(
        app_id: uuid.UUID, entity_id: uuid.UUID, record_id: uuid.UUID, filename: str
    ) -> str:
        """Deterministic S3 key: files/{app}/{entity}/{record}/{uuid}_{filename}"""
        safe = filename.replace("/", "_").replace("..", "_")
        return f"files/{app_id}/{entity_id}/{record_id}/{uuid.uuid4()}_{safe}"


@lru_cache(maxsize=1)
def get_storage() -> S3Storage:
    return S3Storage()
