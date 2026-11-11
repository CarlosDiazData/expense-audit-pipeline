from datetime import date
from decimal import Decimal

from expense_audit.adapters.bigquery import BigQueryRepository, build_merge_expense_sql


class FakeRow:
    def __init__(self, data):
        self._data = data

    def __iter__(self):
        return iter(self._data.values())

    def keys(self):
        return self._data.keys()

    def __getitem__(self, key):
        return self._data[key]

    def items(self):
        return self._data.items()


class FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return [FakeRow(row) for row in self._rows]


class FakeClient:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.queries = []

    def query(self, sql, job_config=None):
        rows = self.results.pop(0) if self.results else []
        self.queries.append((sql, job_config, rows))
        return FakeJob(rows)


def repo(results=None):
    client = FakeClient(results)
    return BigQueryRepository(client, project="demo-project", dataset="expense_audit"), client


def params(job_config):
    return {parameter.name: parameter for parameter in job_config.query_parameters}


def test_merge_sql_is_idempotent_on_source_object():
    sql = build_merge_expense_sql("`p.d.expenses`")
    assert sql.startswith("MERGE `p.d.expenses` AS target")
    assert "ON target.source_object = source.source_object" in sql
    assert "WHEN MATCHED THEN UPDATE SET" in sql
    assert "WHEN NOT MATCHED THEN INSERT" in sql
    assert "created_at" not in sql.split("WHEN MATCHED")[1].split("WHEN NOT MATCHED")[0]


def test_get_status_returns_row_or_none():
    adapter, client = repo([[{"upload_id": "u1", "status": "PENDING", "attempts": 0}]])

    row = adapter.get_status("u1")

    assert row["status"] == "PENDING"
    assert params(client.queries[0][1])["upload_id"].value == "u1"
    assert adapter.get_status("missing") is None


def test_create_pending_inserts_row():
    adapter, client = repo()

    adapter.create_pending("u1", "ticket.pdf")

    sql, job_config, _ = client.queries[0]
    assert "INSERT INTO `p.d.expenses`" not in sql
    assert "processing_status" in sql
    values = params(job_config)
    assert values["upload_id"].value == "u1"
    assert values["original_filename"].value == "ticket.pdf"


def test_set_processing_merges_and_increments_attempts():
    adapter, client = repo()

    adapter.set_processing("u1", "ticket.pdf")

    sql, job_config, _ = client.queries[0]
    assert "MERGE `demo-project.expense_audit.processing_status`" in sql
    assert "attempts = target.attempts + 1" in sql
    assert params(job_config)["upload_id"].value == "u1"


def test_mark_completed_and_failed_update_status():
    adapter, client = repo()

    adapter.mark_completed("u1")
    adapter.mark_failed("u1", "EXTRACTION_FAILED", "Extraction failed")

    completed_sql, completed_config, _ = client.queries[0]
    failed_sql, failed_config, _ = client.queries[1]
    assert "status = 'COMPLETED'" in completed_sql
    assert params(completed_config)["upload_id"].value == "u1"
    assert "status = 'FAILED'" in failed_sql
    failed_params = params(failed_config)
    assert failed_params["error_code"].value == "EXTRACTION_FAILED"
    assert failed_params["error_message"].value == "Extraction failed"


def test_merge_expense_parameterizes_all_columns():
    adapter, client = repo()
    row = {
        "expense_id": "e1",
        "upload_id": "u1",
        "source_object": "gs://bucket/uploads/u1/ticket.pdf",
        "original_filename": "ticket.pdf",
        "rfc_emisor": "ABC010101AB1",
        "rfc_receptor": None,
        "expense_date": "2026-11-05",
        "subtotal": "40.00",
        "iva": "6.40",
        "total": "46.40",
        "currency": "MXN",
        "category": "FOOD",
        "vendor_name": "Taqueria",
        "description": "Lunch",
        "policy_status": "VALID",
        "policy_reasons": [],
        "policy_details": "{}",
        "llm_model": "gemini-2.5-flash",
        "llm_raw_response": "{}",
    }

    adapter.merge_expense(row)

    sql, job_config, _ = client.queries[0]
    assert sql.startswith("MERGE `demo-project.expense_audit.expenses`")
    values = params(job_config)
    assert values["source_object"].value == row["source_object"]
    assert values["policy_reasons"].values == []
    assert values["expense_date"].value == date(2026, 11, 5)


def test_find_duplicate_excludes_current_upload():
    adapter, client = repo([[{"expense_id": "e9"}]])

    found = adapter.find_duplicate("ABC010101AB1", Decimal("10.00"), date(2026, 11, 5), "u1")

    assert found == "e9"
    sql, job_config, _ = client.queries[0]
    assert "upload_id != @upload_id" in sql
    values = params(job_config)
    assert values["rfc_emisor"].value == "ABC010101AB1"
    assert values["expense_date"].value == date(2026, 11, 5)


def test_find_duplicate_returns_none_without_row():
    adapter, _ = repo([[]])
    assert adapter.find_duplicate("A", Decimal("1"), date(2026, 1, 1), "u1") is None


def test_monthly_spend_returns_decimal():
    adapter, client = repo([[{"spend": Decimal("120.50")}]])

    spend = adapter.monthly_spend("FOOD", 2026, 11, exclude_upload_id="u1")

    assert spend == Decimal("120.50")
    sql, job_config, _ = client.queries[0]
    assert "policy_status != 'NON_DEDUCTIBLE'" in sql
    assert "upload_id != @exclude_upload_id" in sql
    values = params(job_config)
    assert values["category"].value == "FOOD"
    assert values["year"].value == 2026
    assert values["month"].value == 11
    assert values["exclude_upload_id"].value == "u1"


def test_monthly_spend_defaults_to_zero():
    adapter, _ = repo([[{"spend": None}]])
    assert adapter.monthly_spend("FOOD", 2026, 11) == Decimal("0")


def test_load_active_limits_maps_rows():
    adapter, client = repo(
        [
            [
                {
                    "category": "FOOD",
                    "per_expense_limit": Decimal("50"),
                    "monthly_limit": Decimal("500"),
                    "currency": "MXN",
                    "active": True,
                }
            ]
        ]
    )

    limits = adapter.load_active_limits()

    assert len(limits) == 1
    assert limits[0].category.value == "FOOD"
    assert limits[0].per_expense_limit == Decimal("50")
    assert "WHERE active" in client.queries[0][0]


def test_get_expense_by_upload_returns_mapping():
    adapter, client = repo([[{"expense_id": "e1", "total": Decimal("46.40")}]])

    row = adapter.get_expense_by_upload("u1")

    assert row["expense_id"] == "e1"
    assert "upload_id = @upload_id" in client.queries[0][0]
