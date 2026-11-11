from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Runtime configuration shared by the upload service and the processor."""

    gcp_project: str = ""
    bq_dataset: str = "expense_audit"
    landing_bucket: str = ""
    access_code_secret: str = "expense-audit-access-code"
    max_upload_mb: int = 10
    rate_limit_per_hour: int = 10
    gemini_model: str = "gemini-2.5-flash"
    gemini_location: str = "us-central1"
    company_rfc: str | None = None
    gcs_allowed_bucket: str = ""
    max_attempts: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if env is None else env
        return cls(
            gcp_project=values.get("GCP_PROJECT", ""),
            bq_dataset=values.get("BQ_DATASET", "expense_audit"),
            landing_bucket=values.get("LANDING_BUCKET", ""),
            access_code_secret=values.get("ACCESS_CODE_SECRET", "expense-audit-access-code"),
            max_upload_mb=int(values.get("MAX_UPLOAD_MB", "10")),
            rate_limit_per_hour=int(values.get("RATE_LIMIT_PER_HOUR", "10")),
            gemini_model=values.get("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_location=values.get("GEMINI_LOCATION", "us-central1"),
            company_rfc=values.get("COMPANY_RFC") or None,
            gcs_allowed_bucket=values.get("GCS_ALLOWED_BUCKET", ""),
            max_attempts=int(values.get("MAX_ATTEMPTS", "5")),
        )
