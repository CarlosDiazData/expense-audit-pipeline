from datetime import date
from decimal import Decimal

import pytest

from expense_audit.adapters.gemini import GeminiExtractor
from expense_audit.domain.errors import DocumentError
from expense_audit.domain.models import Category, ExtractedExpense


class FakeResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class TransientError(Exception):
    code = 503


class FakeModels:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, results):
        self.models = FakeModels(results)


def extractor(results, **kwargs):
    sleeps = []
    adapter = GeminiExtractor(
        FakeClient(results),
        model="gemini-2.5-flash",
        sleep=sleeps.append,
        **kwargs,
    )
    return adapter, sleeps


def extracted() -> ExtractedExpense:
    return ExtractedExpense(
        rfc_emisor="ABC010101AB1",
        rfc_receptor="XYZ010101XY2",
        expense_date=date(2026, 11, 5),
        subtotal=Decimal("100.00"),
        iva=Decimal("16.00"),
        total=Decimal("116.00"),
        currency="MXN",
        category=Category.FOOD,
        vendor_name="Taqueria",
        description="Working lunch",
    )


def test_parses_pydantic_payload_and_sends_structured_config():
    adapter, _ = extractor([FakeResponse(parsed=extracted())])

    result = adapter.extract(b"%PDF-1.4", "application/pdf")

    assert result == extracted()
    call = adapter.client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is ExtractedExpense
    assert len(call["contents"]) == 2


def test_parses_json_text_when_parsed_is_empty():
    payload = (
        '{"rfc_emisor":"ABC010101AB1","rfc_receptor":"XYZ010101XY2",'
        '"expense_date":"2026-11-05","subtotal":"100.00","iva":"16.00",'
        '"total":"116.00","currency":"MXN","category":"FOOD",'
        '"vendor_name":"Taqueria","description":"Working lunch"}'
    )
    adapter, _ = extractor([FakeResponse(parsed=None, text=payload)])

    result = adapter.extract(b"%PDF-1.4", "application/pdf")

    assert result.total == Decimal("116.00")
    assert result.category == Category.FOOD


def test_retries_transient_errors_with_exponential_backoff():
    adapter, sleeps = extractor(
        [TransientError("boom"), TransientError("boom"), FakeResponse(parsed=extracted())]
    )

    result = adapter.extract(b"%PDF-1.4", "application/pdf")

    assert result == extracted()
    assert sleeps == [1.0, 2.0]


def test_exhausted_retries_raise_extraction_failed():
    adapter, _ = extractor([TransientError("boom"), TransientError("boom"), TransientError("boom")])

    with pytest.raises(DocumentError) as error:
        adapter.extract(b"%PDF-1.4", "application/pdf")

    assert error.value.code == "EXTRACTION_FAILED"


def test_non_transient_error_is_not_retried():
    adapter, sleeps = extractor([ValueError("bad request")])

    with pytest.raises(DocumentError) as error:
        adapter.extract(b"%PDF-1.4", "application/pdf")

    assert error.value.code == "EXTRACTION_FAILED"
    assert sleeps == []
    assert len(adapter.client.models.calls) == 1


def test_schema_invalid_text_raises_extraction_failed():
    adapter, _ = extractor([FakeResponse(parsed=None, text='{"total":"not-a-number"}')])

    with pytest.raises(DocumentError) as error:
        adapter.extract(b"%PDF-1.4", "application/pdf")

    assert error.value.code == "EXTRACTION_FAILED"


def test_empty_document_is_unsupported():
    adapter, _ = extractor([])

    with pytest.raises(DocumentError) as error:
        adapter.extract(b"", "application/pdf")

    assert error.value.code == "UNSUPPORTED_DOCUMENT"


def test_blank_currency_defaults_to_mxn():
    parsed = extracted()
    parsed.currency = ""
    adapter, _ = extractor([FakeResponse(parsed=parsed)])

    assert adapter.extract(b"%PDF-1.4", "application/pdf").currency == "MXN"


def test_encrypted_pdf_is_unsupported_without_calling_gemini():
    adapter, _ = extractor([])

    with pytest.raises(DocumentError) as error:
        adapter.extract(b"%PDF-1.4\n1 0 obj << /Encrypt 2 0 R >>", "application/pdf")

    assert error.value.code == "UNSUPPORTED_DOCUMENT"
    assert adapter.client.models.calls == []
