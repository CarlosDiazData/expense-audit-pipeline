from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from google.cloud import bigquery

from ..domain.models import Category, CategoryLimit

EXPENSE_COLUMNS = (
    "expense_id",
    "upload_id",
    "source_object",
    "original_filename",
    "rfc_emisor",
    "rfc_receptor",
    "expense_date",
    "subtotal",
    "iva",
    "total",
    "currency",
    "category",
    "vendor_name",
    "description",
    "policy_status",
    "policy_reasons",
    "policy_details",
    "llm_model",
    "llm_raw_response",
)


def build_merge_expense_sql(table: str) -> str:
    return f"""\
MERGE {table} AS target
USING (
  SELECT
    @expense_id AS expense_id,
    @upload_id AS upload_id,
    @source_object AS source_object,
    @original_filename AS original_filename,
    @rfc_emisor AS rfc_emisor,
    @rfc_receptor AS rfc_receptor,
    CAST(@expense_date AS DATE) AS expense_date,
    CAST(@subtotal AS NUMERIC) AS subtotal,
    CAST(@iva AS NUMERIC) AS iva,
    CAST(@total AS NUMERIC) AS total,
    @currency AS currency,
    @category AS category,
    @vendor_name AS vendor_name,
    @description AS description,
    @policy_status AS policy_status,
    @policy_reasons AS policy_reasons,
    PARSE_JSON(@policy_details) AS policy_details,
    @llm_model AS llm_model,
    PARSE_JSON(@llm_raw_response) AS llm_raw_response,
    CURRENT_TIMESTAMP() AS created_at,
    CURRENT_TIMESTAMP() AS processed_at
) AS source
ON target.source_object = source.source_object
WHEN MATCHED THEN UPDATE SET
  upload_id = source.upload_id,
  original_filename = source.original_filename,
  rfc_emisor = source.rfc_emisor,
  rfc_receptor = source.rfc_receptor,
  expense_date = source.expense_date,
  subtotal = source.subtotal,
  iva = source.iva,
  total = source.total,
  currency = source.currency,
  category = source.category,
  vendor_name = source.vendor_name,
  description = source.description,
  policy_status = source.policy_status,
  policy_reasons = source.policy_reasons,
  policy_details = source.policy_details,
  llm_model = source.llm_model,
  llm_raw_response = source.llm_raw_response,
  processed_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  expense_id, upload_id, source_object, original_filename, rfc_emisor, rfc_receptor,
  expense_date, subtotal, iva, total, currency, category, vendor_name, description,
  policy_status, policy_reasons, policy_details, llm_model, llm_raw_response,
  created_at, processed_at
) VALUES (
  source.expense_id, source.upload_id, source.source_object, source.original_filename,
  source.rfc_emisor, source.rfc_receptor, source.expense_date, source.subtotal,
  source.iva, source.total, source.currency, source.category, source.vendor_name,
  source.description, source.policy_status, source.policy_reasons,
  source.policy_details, source.llm_model, source.llm_raw_response,
  source.created_at, source.processed_at
)
"""


def _scalar(name: str, value: Any, type_: str | None = None) -> bigquery.ScalarQueryParameter:
    return bigquery.ScalarQueryParameter(name, type_, value)


class BigQueryRepository:
    """BigQuery persistence for statuses, expenses, limits, and budget queries."""

    def __init__(self, client: Any, project: str, dataset: str) -> None:
        self._client = client
        self._expenses = f"`{project}.{dataset}.expenses`"
        self._status = f"`{project}.{dataset}.processing_status`"
        self._limits = f"`{project}.{dataset}.category_limits`"

    def _select(self, sql: str, parameters: list[Any]) -> list[dict[str, Any]]:
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        job = self._client.query(sql, job_config=config)
        return [dict(row.items()) for row in job.result()]

    def _execute(self, sql: str, parameters: list[Any]) -> None:
        config = bigquery.QueryJobConfig(query_parameters=parameters)
        self._client.query(sql, job_config=config).result()

    def get_status(self, upload_id: str) -> dict[str, Any] | None:
        rows = self._select(
            f"""\
SELECT upload_id, original_filename, status, attempts, error_code, error_message,
       created_at, updated_at
FROM {self._status}
WHERE upload_id = @upload_id
LIMIT 1
""",
            [_scalar("upload_id", upload_id, "STRING")],
        )
        return rows[0] if rows else None

    def create_pending(self, upload_id: str, original_filename: str) -> None:
        self._execute(
            f"""\
INSERT INTO {self._status}
  (upload_id, original_filename, status, attempts, created_at, updated_at)
VALUES
  (@upload_id, @original_filename, 'PENDING', 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
""",
            [
                _scalar("upload_id", upload_id, "STRING"),
                _scalar("original_filename", original_filename, "STRING"),
            ],
        )

    def set_processing(self, upload_id: str, original_filename: str) -> None:
        self._execute(
            f"""\
MERGE {self._status} AS target
USING (
  SELECT @upload_id AS upload_id, @original_filename AS original_filename
) AS source
ON target.upload_id = source.upload_id
WHEN MATCHED THEN UPDATE SET
  status = 'PROCESSING',
  attempts = target.attempts + 1,
  error_code = NULL,
  error_message = NULL,
  updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (upload_id, original_filename, status, attempts, created_at, updated_at)
VALUES
  (source.upload_id, source.original_filename, 'PROCESSING', 1,
   CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
""",
            [
                _scalar("upload_id", upload_id, "STRING"),
                _scalar("original_filename", original_filename, "STRING"),
            ],
        )

    def mark_completed(self, upload_id: str) -> None:
        self._execute(
            f"""\
UPDATE {self._status}
SET status = 'COMPLETED', error_code = NULL, error_message = NULL,
    updated_at = CURRENT_TIMESTAMP()
WHERE upload_id = @upload_id
""",
            [_scalar("upload_id", upload_id, "STRING")],
        )

    def mark_failed(self, upload_id: str, error_code: str, error_message: str) -> None:
        self._execute(
            f"""\
UPDATE {self._status}
SET status = 'FAILED', error_code = @error_code, error_message = @error_message,
    updated_at = CURRENT_TIMESTAMP()
WHERE upload_id = @upload_id
""",
            [
                _scalar("upload_id", upload_id, "STRING"),
                _scalar("error_code", error_code, "STRING"),
                _scalar("error_message", error_message, "STRING"),
            ],
        )

    def merge_expense(self, row: dict[str, Any]) -> None:
        parameters: list[Any] = []
        for column in EXPENSE_COLUMNS:
            if column == "policy_reasons":
                parameters.append(
                    bigquery.ArrayQueryParameter(column, "STRING", row.get(column) or [])
                )
            elif column in {"policy_details", "llm_raw_response"}:
                parameters.append(_scalar(column, row.get(column) or "{}", "STRING"))
            elif column in {"subtotal", "iva", "total"}:
                parameters.append(_scalar(column, row.get(column), "NUMERIC"))
            elif column == "expense_date":
                parameters.append(_scalar(column, row.get(column), "DATE"))
            else:
                parameters.append(_scalar(column, row.get(column), "STRING"))
        self._execute(build_merge_expense_sql(self._expenses), parameters)

    def get_expense_by_upload(self, upload_id: str) -> dict[str, Any] | None:
        rows = self._select(
            f"""\
SELECT expense_id, upload_id, source_object, original_filename, rfc_emisor,
       rfc_receptor, expense_date, subtotal, iva, total, currency, category,
       vendor_name, description, policy_status, policy_reasons, policy_details,
       llm_model, created_at, processed_at
FROM {self._expenses}
WHERE upload_id = @upload_id
ORDER BY processed_at DESC
LIMIT 1
""",
            [_scalar("upload_id", upload_id, "STRING")],
        )
        return rows[0] if rows else None

    def find_duplicate(
        self,
        rfc_emisor: str,
        total: Decimal,
        expense_date: date,
        upload_id: str,
    ) -> str | None:
        rows = self._select(
            f"""\
SELECT expense_id
FROM {self._expenses}
WHERE rfc_emisor = @rfc_emisor
  AND total = @total
  AND expense_date = @expense_date
  AND upload_id != @upload_id
LIMIT 1
""",
            [
                _scalar("rfc_emisor", rfc_emisor, "STRING"),
                _scalar("total", total, "NUMERIC"),
                _scalar("expense_date", expense_date.isoformat(), "DATE"),
                _scalar("upload_id", upload_id, "STRING"),
            ],
        )
        return str(rows[0]["expense_id"]) if rows else None

    def monthly_spend(self, category: str, year: int, month: int) -> Decimal:
        rows = self._select(
            f"""\
SELECT COALESCE(SUM(total), 0) AS spend
FROM {self._expenses}
WHERE category = @category
  AND DATE_TRUNC(expense_date, MONTH) = DATE(@year, @month, 1)
  AND policy_status != 'NON_DEDUCTIBLE'
""",
            [
                _scalar("category", category, "STRING"),
                _scalar("year", year, "INT64"),
                _scalar("month", month, "INT64"),
            ],
        )
        value = rows[0]["spend"] if rows else None
        return Decimal(str(value)) if value is not None else Decimal("0")

    def load_active_limits(self) -> list[CategoryLimit]:
        rows = self._select(
            f"""\
SELECT category, per_expense_limit, monthly_limit, currency, active
FROM {self._limits}
WHERE active
""",
            [],
        )
        return [
            CategoryLimit(
                category=Category(row["category"]),
                per_expense_limit=Decimal(str(row["per_expense_limit"])),
                monthly_limit=Decimal(str(row["monthly_limit"])),
                currency=str(row["currency"]),
                active=bool(row["active"]),
            )
            for row in rows
        ]
