import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from expense_audit.config import Settings
from expense_audit.domain.errors import DocumentError
from expense_audit.domain.models import Category, CategoryLimit, ExtractedExpense
from expense_audit.processor import (
    ProcessorDeps,
    build_expense_row,
    parse_object_path,
    run_processing,
)

BUCKET = "landing-bucket"
OBJECT = "uploads/u1/ticket.pdf"

LIMITS = [
    CategoryLimit(
        category=Category.FOOD, per_expense_limit=Decimal("50"), monthly_limit=Decimal("500")
    ),
    CategoryLimit(
        category=Category.TRANSPORT,
        per_expense_limit=Decimal("200"),
        monthly_limit=Decimal("2000"),
    ),
    CategoryLimit(
        category=Category.SOFTWARE,
        per_expense_limit=Decimal("500"),
        monthly_limit=Decimal("3000"),
    ),
    CategoryLimit(
        category=Category.LODGING, per_expense_limit=Decimal("300"), monthly_limit=Decimal("3000")
    ),
    CategoryLimit(
        category=Category.OTHER, per_expense_limit=Decimal("100"), monthly_limit=Decimal("1000")
    ),
]


def valid_expense(**overrides) -> ExtractedExpense:
    base = {
        "rfc_emisor": "ABC010101AB1",
        "rfc_receptor": "XYZ010101XY2",
        "expense_date": date(2026, 11, 5),
        "subtotal": Decimal("40.00"),
        "iva": Decimal("6.40"),
        "total": Decimal("46.40"),
        "currency": "MXN",
        "category": Category.FOOD,
        "vendor_name": "Taqueria",
        "description": "Working lunch",
    }
    base.update(overrides)
    return ExtractedExpense(**base)


class FakeRepo:
    def __init__(self, limits=None, duplicate=None, spend=Decimal("0")):
        self.statuses = {}
        self.limits = limits if limits is not None else LIMITS
        self.duplicate = duplicate
        self.spend = spend
        self.merged = []
        self.monthly_calls = 0
        self.calls = []

    def get_status(self, upload_id):
        return self.statuses.get(upload_id)

    def set_processing(self, upload_id, original_filename):
        row = self.statuses.setdefault(
            upload_id,
            {
                "upload_id": upload_id,
                "original_filename": original_filename,
                "status": "PENDING",
                "attempts": 0,
                "error_code": None,
                "error_message": None,
            },
        )
        row["status"] = "PROCESSING"
        row["attempts"] += 1
        self.calls.append(("set_processing", upload_id))

    def mark_completed(self, upload_id):
        self.statuses[upload_id]["status"] = "COMPLETED"
        self.calls.append(("mark_completed", upload_id))

    def mark_failed(self, upload_id, error_code, error_message):
        self.statuses.setdefault(upload_id, {"upload_id": upload_id, "attempts": 0})
        self.statuses[upload_id].update(
            status="FAILED", error_code=error_code, error_message=error_message
        )
        self.calls.append(("mark_failed", upload_id))

    def load_active_limits(self):
        return self.limits

    def find_duplicate(self, rfc_emisor, total, expense_date, upload_id):
        return self.duplicate

    def monthly_spend(self, category, year, month, exclude_upload_id=None):
        self.monthly_calls += 1
        self.monthly_exclusion = exclude_upload_id
        return self.spend

    def merge_expense(self, row):
        self.merged.append(row)


class FakeStorage:
    def __init__(self, content=b"%PDF-1.4", mime_type="application/pdf", error=None):
        self.content = content
        self.mime_type = mime_type
        self.error = error
        self.calls = []

    def download(self, path, max_bytes):
        self.calls.append((path, max_bytes))
        if self.error is not None:
            raise self.error
        return self.content, self.mime_type


class FakeExtractor:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else valid_expense()
        self.error = error
        self.calls = []

    def extract(self, content, mime_type):
        self.calls.append((content, mime_type))
        if self.error is not None:
            raise self.error
        return self.result


def deps(
    *,
    repo=None,
    storage=None,
    extractor=None,
    company_rfc=None,
    allowed_bucket=BUCKET,
    max_attempts=5,
):
    return ProcessorDeps(
        repo=repo or FakeRepo(),
        storage=storage or FakeStorage(),
        extractor=extractor or FakeExtractor(),
        settings=Settings(
            gcp_project="demo",
            bq_dataset="expense_audit",
            landing_bucket=BUCKET,
            gcs_allowed_bucket=allowed_bucket,
            company_rfc=company_rfc,
            max_attempts=max_attempts,
        ),
        clock=lambda: datetime(2026, 11, 11, 12, 0, tzinfo=UTC),
    )


def event(name=OBJECT, bucket=BUCKET):
    return {"bucket": bucket, "name": name}


def test_parse_object_path_requires_uploads_prefix():
    assert parse_object_path("uploads/u1/ticket.pdf") == ("u1", "ticket.pdf")
    assert parse_object_path("uploads/u1/nested/ticket.pdf") == ("u1", "nested/ticket.pdf")
    assert parse_object_path("other/u1/ticket.pdf") is None
    assert parse_object_path("uploads/u1") is None


def test_happy_path_completes_and_merges_one_valid_expense():
    repo = FakeRepo()
    result = run_processing(event(), deps(repo=repo))

    assert result == "completed"
    assert repo.statuses["u1"]["status"] == "COMPLETED"
    assert repo.statuses["u1"]["attempts"] == 1
    assert len(repo.merged) == 1
    row = repo.merged[0]
    assert row["source_object"] == f"gs://{BUCKET}/{OBJECT}"
    assert row["policy_status"] == "VALID"
    assert json.loads(row["policy_details"]) == {}
    assert row["rfc_emisor"] == "ABC010101AB1"
    assert row["category"] == "FOOD"
    assert repo.monthly_calls == 1
    assert repo.monthly_exclusion == "u1"


def test_duplicate_delivery_short_circuits_on_completed():
    repo = FakeRepo()
    repo.statuses["u1"] = {
        "upload_id": "u1",
        "status": "COMPLETED",
        "attempts": 1,
        "error_code": None,
        "error_message": None,
    }
    storage = FakeStorage()

    result = run_processing(event(), deps(repo=repo, storage=storage))

    assert result == "completed"
    assert repo.merged == []
    assert storage.calls == []
    assert ("set_processing", "u1") not in repo.calls


def test_retry_exhaustion_marks_failed_without_processing():
    repo = FakeRepo()
    repo.statuses["u1"] = {
        "upload_id": "u1",
        "status": "PROCESSING",
        "attempts": 5,
        "error_code": None,
        "error_message": None,
    }
    storage = FakeStorage()

    result = run_processing(event(), deps(repo=repo, storage=storage))

    assert result == "retry_exhausted"
    assert repo.statuses["u1"]["status"] == "FAILED"
    assert repo.statuses["u1"]["error_code"] == "RETRY_EXHAUSTED"
    assert storage.calls == []
    assert repo.merged == []


def test_document_error_marks_failed_and_swallows():
    repo = FakeRepo()
    extractor = FakeExtractor(error=DocumentError("EXTRACTION_FAILED", "Extraction failed"))

    result = run_processing(event(), deps(repo=repo, extractor=extractor))

    assert result == "failed"
    assert repo.statuses["u1"]["status"] == "FAILED"
    assert repo.statuses["u1"]["error_code"] == "EXTRACTION_FAILED"
    assert repo.merged == []


def test_oversized_download_marks_file_too_large():
    repo = FakeRepo()
    storage = FakeStorage(error=DocumentError("FILE_TOO_LARGE", "Document exceeds the size limit"))
    extractor = FakeExtractor()

    result = run_processing(event(), deps(repo=repo, storage=storage, extractor=extractor))

    assert result == "failed"
    assert repo.statuses["u1"]["error_code"] == "FILE_TOO_LARGE"
    assert extractor.calls == []


def test_infrastructure_error_propagates_for_eventarc_retry():
    repo = FakeRepo()
    storage = FakeStorage(error=RuntimeError("bigquery unavailable"))

    with pytest.raises(RuntimeError):
        run_processing(event(), deps(repo=repo, storage=storage))

    assert repo.statuses["u1"]["status"] == "PROCESSING"
    assert repo.merged == []


def test_over_limit_expense_is_suspicious():
    repo = FakeRepo()
    extractor = FakeExtractor(
        result=valid_expense(
            category=Category.TRANSPORT,
            total=Decimal("350.00"),
            subtotal=Decimal("301.72"),
            iva=Decimal("48.28"),
        )
    )

    run_processing(event(), deps(repo=repo, extractor=extractor))

    row = repo.merged[0]
    assert row["policy_status"] == "SUSPICIOUS"
    assert "PER_EXPENSE_LIMIT_EXCEEDED" in row["policy_reasons"]


def test_duplicate_expense_marks_suspicious():
    repo = FakeRepo(duplicate="expense-old")

    run_processing(event(), deps(repo=repo))

    row = repo.merged[0]
    assert row["policy_status"] == "SUSPICIOUS"
    assert "DUPLICATE_EXPENSE" in row["policy_reasons"]
    details = json.loads(row["policy_details"])
    assert details["DUPLICATE_EXPENSE"]["expense_id"] == "expense-old"


def test_non_mxn_skips_monthly_query():
    repo = FakeRepo()
    extractor = FakeExtractor(result=valid_expense(currency="USD"))

    run_processing(event(), deps(repo=repo, extractor=extractor))

    assert repo.monthly_calls == 0
    assert repo.merged[0]["policy_status"] == "SUSPICIOUS"
    assert repo.merged[0]["policy_reasons"] == ["CURRENCY_UNSUPPORTED"]


def test_company_receptor_mismatch_is_non_deductible():
    repo = FakeRepo()

    run_processing(event(), deps(repo=repo, company_rfc="QWE010101QW3"))

    row = repo.merged[0]
    assert row["policy_status"] == "NON_DEDUCTIBLE"
    assert "RECEPTOR_NOT_COMPANY" in row["policy_reasons"]


def test_bucket_mismatch_is_ignored():
    repo = FakeRepo()
    storage = FakeStorage()

    result = run_processing(event(bucket="other-bucket"), deps(repo=repo, storage=storage))

    assert result == "ignored"
    assert storage.calls == []
    assert repo.merged == []


def test_malformed_event_is_ignored():
    repo = FakeRepo()
    assert run_processing({"bucket": BUCKET}, deps(repo=repo)) == "ignored"
    assert run_processing({"name": OBJECT}, deps(repo=repo)) == "ignored"
    assert repo.merged == []


def test_object_outside_uploads_prefix_is_ignored():
    repo = FakeRepo()
    assert run_processing(event(name="other/u1/ticket.pdf"), deps(repo=repo)) == "ignored"
    assert repo.merged == []


def test_build_expense_row_serializes_policy_and_raw_response():
    from expense_audit.domain.policy import evaluate_policy

    expense = valid_expense()
    decision = evaluate_policy(
        expense, LIMITS, today=date(2026, 11, 11), monthly_spend=Decimal("0")
    )
    row = build_expense_row(
        upload_id="u1",
        bucket=BUCKET,
        object_name=OBJECT,
        filename="ticket.pdf",
        extracted=expense,
        decision=decision,
        model="gemini-2.5-flash",
    )

    assert row["source_object"] == f"gs://{BUCKET}/{OBJECT}"
    assert row["expense_date"] == "2026-11-05"
    assert row["subtotal"] == "40.00"
    assert row["policy_reasons"] == []
    assert json.loads(row["llm_raw_response"])["category"] == "FOOD"
    assert row["llm_model"] == "gemini-2.5-flash"


def test_build_expense_row_nulls_missing_values():
    from expense_audit.domain.policy import evaluate_policy

    expense = valid_expense(rfc_receptor=None, expense_date=None, subtotal=None, iva=None)
    decision = evaluate_policy(expense, LIMITS, today=date(2026, 11, 11))
    row = build_expense_row(
        upload_id="u1",
        bucket=BUCKET,
        object_name=OBJECT,
        filename="ticket.pdf",
        extracted=expense,
        decision=decision,
        model="gemini-2.5-flash",
    )

    assert row["rfc_receptor"] is None
    assert row["expense_date"] is None
    assert row["subtotal"] is None
    assert row["policy_status"] == "NON_DEDUCTIBLE"
