from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import Settings
from .domain.errors import DocumentError
from .domain.models import ExtractedExpense, PolicyDecision
from .domain.policy import evaluate_policy
from .domain.validation import money, normalize_rfc

UPLOADS_PREFIX = "uploads/"
LOGGER = logging.getLogger(__name__)


def _log(
    event: str, *, upload_id: str | None = None, source_object: str | None = None, **fields
) -> None:
    payload = {"event": event, "upload_id": upload_id, "source_object": source_object}
    payload.update(fields)
    LOGGER.info(json.dumps(payload, separators=(",", ":")))


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class ProcessorDeps:
    repo: Any
    storage: Any
    extractor: Any
    settings: Settings
    clock: Callable[[], datetime] = field(default=_utcnow)


def parse_object_path(object_name: str) -> tuple[str, str] | None:
    parts = object_name.split("/")
    if len(parts) < 3 or parts[0] != UPLOADS_PREFIX.rstrip("/") or not parts[1]:
        return None
    return parts[1], "/".join(parts[2:])


def build_expense_row(
    *,
    upload_id: str,
    bucket: str,
    object_name: str,
    filename: str,
    extracted: ExtractedExpense,
    decision: PolicyDecision,
    model: str,
) -> dict[str, Any]:
    return {
        "expense_id": str(uuid.uuid4()),
        "upload_id": upload_id,
        "source_object": f"gs://{bucket}/{object_name}",
        "original_filename": filename,
        "rfc_emisor": normalize_rfc(extracted.rfc_emisor),
        "rfc_receptor": normalize_rfc(extracted.rfc_receptor),
        "expense_date": extracted.expense_date.isoformat() if extracted.expense_date else None,
        "subtotal": money(extracted.subtotal) if extracted.subtotal is not None else None,
        "iva": money(extracted.iva) if extracted.iva is not None else None,
        "total": money(extracted.total) if extracted.total is not None else None,
        "currency": extracted.currency.strip().upper() or "MXN",
        "category": extracted.category.value,
        "vendor_name": extracted.vendor_name,
        "description": extracted.description,
        "policy_status": decision.status.value,
        "policy_reasons": [reason.value for reason in decision.reasons],
        "policy_details": json.dumps(decision.details, ensure_ascii=False, separators=(",", ":")),
        "llm_model": model,
        "llm_raw_response": extracted.model_dump_json(),
    }


def run_processing(payload: dict[str, Any], deps: ProcessorDeps) -> str:
    """Process one finalized GCS object.

    Document-level failures are recorded and swallowed so Eventarc does not retry.
    Infrastructure failures propagate so Eventarc retries the delivery.
    """
    bucket = payload.get("bucket")
    object_name = payload.get("name")
    if not bucket or not object_name:
        return "ignored"

    allowed_bucket = deps.settings.gcs_allowed_bucket or deps.settings.landing_bucket
    if allowed_bucket and bucket != allowed_bucket:
        return "ignored"

    parsed = parse_object_path(object_name)
    if parsed is None:
        return "ignored"
    upload_id, filename = parsed

    status = deps.repo.get_status(upload_id)
    source_object = f"gs://{bucket}/{object_name}"
    if status is not None and status.get("status") == "COMPLETED":
        _log("processing_skipped_completed", upload_id=upload_id, source_object=source_object)
        return "completed"

    attempts = int(status.get("attempts") or 0) if status is not None else 0
    if attempts >= deps.settings.max_attempts:
        deps.repo.mark_failed(upload_id, "RETRY_EXHAUSTED", "Maximum processing attempts reached")
        return "retry_exhausted"

    if status is not None and status.get("original_filename"):
        filename = str(status["original_filename"])
    deps.repo.set_processing(upload_id, filename)

    try:
        content, mime_type = deps.storage.download(
            object_name, deps.settings.max_upload_mb * 1024 * 1024
        )
        extracted = deps.extractor.extract(content, mime_type)
    except DocumentError as exc:
        deps.repo.mark_failed(upload_id, exc.code, exc.message)
        _log(
            "processing_failed",
            upload_id=upload_id,
            source_object=source_object,
            error_code=exc.code,
        )
        return "failed"

    limits = deps.repo.load_active_limits()
    today = deps.clock().date()

    normalized_emisor = normalize_rfc(extracted.rfc_emisor)
    duplicate_of: str | None = None
    if normalized_emisor and extracted.total is not None and extracted.expense_date is not None:
        duplicate_of = deps.repo.find_duplicate(
            normalized_emisor,
            extracted.total,
            extracted.expense_date,
            upload_id,
        )

    monthly_spend = None
    if (
        extracted.total is not None
        and extracted.expense_date is not None
        and extracted.currency.strip().upper() == "MXN"
    ):
        monthly_spend = deps.repo.monthly_spend(
            extracted.category.value,
            extracted.expense_date.year,
            extracted.expense_date.month,
            exclude_upload_id=upload_id,
        )

    decision = evaluate_policy(
        extracted,
        limits,
        today=today,
        company_rfc=deps.settings.company_rfc,
        monthly_spend=monthly_spend,
        duplicate_of=duplicate_of,
    )

    deps.repo.merge_expense(
        build_expense_row(
            upload_id=upload_id,
            bucket=bucket,
            object_name=object_name,
            filename=filename,
            extracted=extracted,
            decision=decision,
            model=deps.settings.gemini_model,
        )
    )
    deps.repo.mark_completed(upload_id)
    _log("processing_completed", upload_id=upload_id, source_object=source_object)
    return "completed"
