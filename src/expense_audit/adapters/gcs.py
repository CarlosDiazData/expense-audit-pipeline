from __future__ import annotations

from typing import Any

from ..domain.errors import DocumentError


class GcsStorage:
    """Landing-bucket object access with a hard download cap."""

    def __init__(self, client: Any, bucket_name: str) -> None:
        self._client = client
        self._bucket_name = bucket_name
        self._bucket = client.bucket(bucket_name)

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        blob = self._bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)

    def download(self, path: str, max_bytes: int) -> tuple[bytes, str]:
        blob = self._bucket.blob(path)
        try:
            blob.reload()
        except Exception as exc:  # noqa: BLE001 - any read failure is document-level
            raise DocumentError("UNSUPPORTED_DOCUMENT", "Document could not be read") from exc

        size = getattr(blob, "size", None)
        if size is not None and int(size) > max_bytes:
            raise DocumentError("FILE_TOO_LARGE", "Document exceeds the size limit")

        try:
            content = blob.download_as_bytes()
        except Exception as exc:  # noqa: BLE001 - any read failure is document-level
            raise DocumentError("UNSUPPORTED_DOCUMENT", "Document could not be read") from exc

        if len(content) > max_bytes:
            raise DocumentError("FILE_TOO_LARGE", "Document exceeds the size limit")

        content_type = getattr(blob, "content_type", None) or "application/octet-stream"
        return content, content_type
