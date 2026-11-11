from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from expense_audit.config import Settings
from expense_audit.domain.models import Category, CategoryLimit, ExtractedExpense
from expense_audit.processor import ProcessorDeps, run_processing

BUCKET = "landing-bucket"
OBJECT = "uploads/u1/ticket.pdf"
LIMITS = [
    CategoryLimit(
        category=Category.FOOD,
        per_expense_limit=Decimal("50.00"),
        monthly_limit=Decimal("500.00"),
    )
]


class RetryRepo:
    def __init__(self):
        self.statuses = {}
        self.rows = {}
        self.prior_spend = Decimal("453.60")
        self.fail_completion = True

    def get_status(self, upload_id):
        return self.statuses.get(upload_id)

    def set_processing(self, upload_id, filename):
        row = self.statuses.setdefault(upload_id, {"attempts": 0})
        row.update(status="PROCESSING", attempts=row["attempts"] + 1)

    def mark_completed(self, upload_id):
        if self.fail_completion:
            self.fail_completion = False
            raise RuntimeError("simulated BigQuery transient failure after MERGE")
        self.statuses[upload_id]["status"] = "COMPLETED"

    def mark_failed(self, upload_id, code, message):
        self.statuses.setdefault(upload_id, {"attempts": 0}).update(
            status="FAILED", error_code=code
        )

    def load_active_limits(self):
        return LIMITS

    def find_duplicate(self, *args):
        return None

    def monthly_spend(self, category, year, month, exclude_upload_id=None):
        total = self.prior_spend
        for upload_id, row in self.rows.items():
            if upload_id == exclude_upload_id:
                continue
            if row["category"] == category and row["policy_status"] != "NON_DEDUCTIBLE":
                total += Decimal(row["total"])
        return total

    def merge_expense(self, row):
        self.rows[row["upload_id"]] = row


class Storage:
    def download(self, path, max_bytes):
        return b"%PDF-1.4", "application/pdf"


class Extractor:
    def extract(self, content, mime_type):
        return ExtractedExpense(
            rfc_emisor="ABC010101AB1",
            rfc_receptor="XYZ010101XY2",
            expense_date=date(2026, 11, 5),
            subtotal=Decimal("40.00"),
            iva=Decimal("6.40"),
            total=Decimal("46.40"),
            currency="MXN",
            category=Category.FOOD,
            vendor_name="Taqueria",
            description="Working lunch",
        )


def deps(repo):
    return ProcessorDeps(
        repo=repo,
        storage=Storage(),
        extractor=Extractor(),
        settings=Settings(gcp_project="demo", landing_bucket=BUCKET, gcs_allowed_bucket=BUCKET),
        clock=lambda: datetime(2026, 11, 11, 12, 0, tzinfo=UTC),
    )


def test_monthly_spend_is_not_double_counted_after_merge_retry():
    repo = RetryRepo()
    event = {"bucket": BUCKET, "name": OBJECT}

    with pytest.raises(RuntimeError):
        run_processing(event, deps(repo))

    first = repo.rows["u1"]
    assert first["policy_status"] == "VALID"
    assert repo.statuses["u1"]["status"] == "PROCESSING"

    assert run_processing(event, deps(repo)) == "completed"

    assert len(repo.rows) == 1
    retried = repo.rows["u1"]
    assert retried["policy_status"] == "VALID"
    assert retried["policy_reasons"] == []
