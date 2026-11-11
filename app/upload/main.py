from __future__ import annotations

import re
import secrets
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from expense_audit.adapters.bigquery import BigQueryRepository
from expense_audit.adapters.gcs import GcsStorage
from expense_audit.adapters.secrets import SecretAccessCodeProvider
from expense_audit.config import Settings

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ALLOWED_TYPES = {
    ".pdf": (b"%PDF-", "application/pdf"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    ".jpg": (b"\xff\xd8\xff", "image/jpeg"),
    ".jpeg": (b"\xff\xd8\xff", "image/jpeg"),
}


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    stem, suffix = name.rsplit(".", 1) if "." in name else (name, "")
    suffix = f".{suffix.lower()}" if suffix else ""
    if suffix not in ALLOWED_TYPES:
        suffix = ""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "upload"
    return f"{stem[:80]}{suffix}"


def detect_content_type(filename: str, content: bytes) -> str | None:
    suffix = Path(filename).suffix.lower()
    candidate = ALLOWED_TYPES.get(suffix)
    if candidate is None:
        return None
    signature, content_type = candidate
    if not content.startswith(signature):
        return None
    return content_type


class SlidingWindowRateLimiter:
    """Best-effort in-memory limiter, per instance as documented."""

    def __init__(
        self,
        limit: int,
        *,
        window_seconds: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            events = [event for event in self._events[key] if now - event < self.window_seconds]
            if len(events) >= self.limit:
                self._events[key] = events
                return False
            events.append(now)
            self._events[key] = events
            return True


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _money(value: Any) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def create_app(
    settings: Settings | None = None,
    *,
    access_code_provider: Any | None = None,
    storage: Any | None = None,
    repo: Any | None = None,
    limiter: SlidingWindowRateLimiter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    access_code_provider = access_code_provider or SecretAccessCodeProvider(
        None, settings.gcp_project, settings.access_code_secret
    )
    if storage is None:
        from google.cloud import storage as gcs

        storage = GcsStorage(gcs.Client(project=settings.gcp_project), settings.landing_bucket)
    if repo is None:
        from google.cloud import bigquery

        repo = BigQueryRepository(
            bigquery.Client(project=settings.gcp_project),
            project=settings.gcp_project,
            dataset=settings.bq_dataset,
        )
    limiter = limiter or SlidingWindowRateLimiter(settings.rate_limit_per_hour)

    app = FastAPI(title="Expense Audit Upload", docs_url=None, redoc_url=None)
    app.state.storage = storage
    app.state.repo = repo
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return TEMPLATES.TemplateResponse(
            request=request,
            name="index.html",
            context={"max_upload_mb": settings.max_upload_mb},
        )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/upload")
    async def upload(
        request: Request,
        code: str = Form(...),
        file: UploadFile = File(...),  # noqa: B008 - FastAPI dependency marker
    ) -> JSONResponse:
        try:
            expected = access_code_provider.get()
        except Exception as exc:  # noqa: BLE001 - secret backend is infrastructure
            raise HTTPException(status_code=503, detail="Access code unavailable") from exc

        if not secrets.compare_digest(code.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(status_code=401, detail="Invalid access code")

        client_ip = request.client.host if request.client else "unknown"
        if not limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Too many uploads, try later")

        content = await file.read()
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail="File exceeds the size limit")

        filename = file.filename or "upload"
        content_type = detect_content_type(filename, content)
        if content_type is None:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        upload_id = str(uuid.uuid4())
        safe_name = sanitize_filename(filename)
        object_path = f"uploads/{upload_id}/{safe_name}"
        try:
            storage.upload(object_path, content, content_type)
            repo.create_pending(upload_id, safe_name)
        except Exception as exc:  # noqa: BLE001 - storage or BigQuery failure
            raise HTTPException(status_code=500, detail="Upload failed") from exc

        return JSONResponse(
            status_code=202,
            content={"upload_id": upload_id, "status": "PENDING"},
        )

    @app.get("/status/{upload_id}")
    def status(upload_id: str) -> dict[str, Any]:
        row = repo.get_status(upload_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown upload")

        payload: dict[str, Any] = {
            "upload_id": upload_id,
            "status": row.get("status"),
            "updated_at": _iso(row.get("updated_at")),
        }
        if row.get("error_code"):
            payload["error_code"] = row["error_code"]

        if row.get("status") == "COMPLETED":
            expense = repo.get_expense_by_upload(upload_id)
            if expense is not None:
                payload["result"] = {
                    "expense_id": expense.get("expense_id"),
                    "rfc_emisor": expense.get("rfc_emisor"),
                    "total": _money(expense.get("total")),
                    "category": expense.get("category"),
                    "expense_date": _iso(expense.get("expense_date")),
                    "policy_status": expense.get("policy_status"),
                    "policy_reasons": expense.get("policy_reasons") or [],
                    "policy_details": expense.get("policy_details") or {},
                }
        return payload

    return app
