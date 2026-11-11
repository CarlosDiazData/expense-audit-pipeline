from __future__ import annotations

from typing import Any


class SecretAccessCodeProvider:
    """Reads the shared access code from Secret Manager and caches it."""

    def __init__(self, client: Any | None, project: str, secret_name: str) -> None:
        self._client = client
        self._project = project
        self._secret_name = secret_name
        self._cached: str | None = None

    def get(self) -> str:
        if self._cached is not None:
            return self._cached
        client = self._client or self._default_client()
        response = client.access_secret_version(
            request={
                "name": (f"projects/{self._project}/secrets/{self._secret_name}/versions/latest")
            }
        )
        value = response.payload.data.decode("utf-8").strip()
        self._cached = value
        return value

    @staticmethod
    def _default_client() -> Any:
        from google.cloud import secretmanager

        return secretmanager.SecretManagerServiceClient()
