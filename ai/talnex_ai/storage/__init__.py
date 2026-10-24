"""File storage: screenshots, videos, resumes and logs go to an S3 bucket (Cloudflare R2 in
production, RustFS locally).

Workers upload what they create. The website never touches the bucket: the Go API hands out
short-lived view links instead.
"""
from __future__ import annotations

import io
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from talnex_ai.settings import S3Settings

_MISSING = {"NoSuchKey", "NoSuchObject", "NotFound"}


class Store:
    def __init__(self, cfg: S3Settings):
        url = urlparse(cfg.endpoint)
        if url.scheme not in ("http", "https") or not url.netloc:
            raise ValueError(f"S3_ENDPOINT must be a full address like http://s3:9000 (got {cfg.endpoint!r})")
        self.bucket = cfg.bucket
        self.client = Minio(
            url.netloc,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            secure=url.scheme == "https",
            region=cfg.region,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if it isn't there yet (local runs start with an empty store)."""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data), content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(self.bucket, key)
        try:
            return response.read()
        finally:
            # Hand the HTTP connection back, or the client slowly runs out of them.
            response.close()
            response.release_conn()

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, key)
        except S3Error as err:
            if err.code in _MISSING:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        """Remove a file. Deleting one that is already gone is fine."""
        self.client.remove_object(self.bucket, key)
