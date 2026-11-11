from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from google.genai import types
from pydantic import ValidationError

from ..domain.errors import DocumentError
from ..domain.models import ExtractedExpense

EXTRACTION_PROMPT = """\
You extract structured data from a single Mexican expense receipt (factura or ticket).

Rules:
- Extract only values the document states. Never invent or infer amounts, dates, or identifiers.
- Return null for any field that is absent or unreadable.
- Copy RFC values exactly as printed; do not correct them.
- Choose the category that best matches the vendor and description. Use OTHER when unclear.
- Categories: FOOD, TRANSPORT, SOFTWARE, LODGING, OTHER.
- currency is an ISO 4217 code; use MXN when the document shows pesos or does not state a currency.
- Return the raw numbers without thousands separators. IVA is the tax amount, not the rate.
"""

TRANSIENT_CODES = frozenset({429, 500, 502, 503, 504})
TRANSIENT_NAMES = frozenset(
    {
        "DeadlineExceeded",
        "InternalServerError",
        "ServerError",
        "ServiceUnavailable",
        "TooManyRequests",
    }
)


def is_transient_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in TRANSIENT_CODES:
        return True
    return type(exc).__name__ in TRANSIENT_NAMES


class GeminiExtractor:
    """Structured extraction through Gemini; the model never decides policy."""

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep

    def extract(self, content: bytes, mime_type: str) -> ExtractedExpense:
        if not content:
            raise DocumentError("UNSUPPORTED_DOCUMENT", "Document is empty")
        if mime_type == "application/pdf" and b"/Encrypt" in content:
            raise DocumentError("UNSUPPORTED_DOCUMENT", "Encrypted documents are not supported")

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Part.from_bytes(data=content, mime_type=mime_type),
                        EXTRACTION_PROMPT,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExtractedExpense,
                        temperature=0,
                    ),
                )
                return self._parse(response)
            except DocumentError:
                raise
            except Exception as exc:  # noqa: BLE001 - classify and convert provider errors
                if attempt < self.max_retries and is_transient_error(exc):
                    self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
                    continue
                raise DocumentError("EXTRACTION_FAILED", "Extraction failed") from exc

        raise DocumentError("EXTRACTION_FAILED", "Extraction failed")

    @staticmethod
    def _parse(response: Any) -> ExtractedExpense:
        parsed = getattr(response, "parsed", None)
        try:
            if isinstance(parsed, ExtractedExpense):
                return GeminiExtractor._normalized(parsed)
            if isinstance(parsed, dict):
                return GeminiExtractor._normalized(ExtractedExpense.model_validate(parsed))
            text = getattr(response, "text", None)
            if text:
                return GeminiExtractor._normalized(ExtractedExpense.model_validate_json(text))
        except ValidationError as exc:
            raise DocumentError(
                "EXTRACTION_FAILED", "Extraction did not match the expected schema"
            ) from exc
        raise DocumentError("EXTRACTION_FAILED", "Extraction returned no structured payload")

    @staticmethod
    def _normalized(expense: ExtractedExpense) -> ExtractedExpense:
        currency = expense.currency.strip().upper() or "MXN"
        if currency == expense.currency:
            return expense
        return expense.model_copy(update={"currency": currency})
