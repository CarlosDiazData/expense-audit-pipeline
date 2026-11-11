from __future__ import annotations


class DocumentError(Exception):
    """A document-level failure that must be recorded, not retried by Eventarc."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
