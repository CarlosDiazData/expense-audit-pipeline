import time

from app.upload.main import SlidingWindowRateLimiter, create_app, sanitize_filename
from fastapi.testclient import TestClient

from expense_audit.config import Settings

CODE = "super-secret-code"
PDF = b"%PDF-1.4\nsynthetic invoice"


class FakeAccessCodeProvider:
    def __init__(self, value=CODE):
        self.value = value

    def get(self):
        return self.value


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def upload(self, path, data, content_type):
        self.objects[path] = (data, content_type)


class FakeRepo:
    def __init__(self):
        self.pending = {}
        self.statuses = {}
        self.expenses = {}

    def create_pending(self, upload_id, original_filename):
        self.pending[upload_id] = original_filename
        self.statuses[upload_id] = {
            "upload_id": upload_id,
            "original_filename": original_filename,
            "status": "PENDING",
            "attempts": 0,
            "error_code": None,
            "updated_at": None,
        }

    def get_status(self, upload_id):
        return self.statuses.get(upload_id)

    def get_expense_by_upload(self, upload_id):
        return self.expenses.get(upload_id)


def build_client(max_upload_mb=10, rate_limit=10):
    app = create_app(
        Settings(
            gcp_project="demo",
            landing_bucket="landing-bucket",
            max_upload_mb=max_upload_mb,
            rate_limit_per_hour=rate_limit,
        ),
        access_code_provider=FakeAccessCodeProvider(),
        storage=FakeStorage(),
        repo=FakeRepo(),
        limiter=SlidingWindowRateLimiter(rate_limit),
    )
    return TestClient(app), app


def upload(client, filename="ticket.pdf", content=PDF, code=CODE):
    return client.post(
        "/upload",
        data={"code": code},
        files={"file": (filename, content, "application/pdf")},
    )


def test_index_renders_spanish_upload_page():
    client, _ = build_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "Auditoría de Gastos" in response.text
    assert "Código de acceso" in response.text


def test_healthz():
    client, _ = build_client()
    assert client.get("/healthz").json() == {"status": "ok"}


def test_wrong_access_code_is_rejected():
    client, _ = build_client()
    response = upload(client, code="wrong")
    assert response.status_code == 401


def test_missing_access_code_is_rejected():
    client, _ = build_client()
    response = client.post("/upload", files={"file": ("ticket.pdf", PDF, "application/pdf")})
    assert response.status_code == 422


def test_oversized_file_is_rejected():
    client, _ = build_client(max_upload_mb=1)
    response = upload(client, content=b"%PDF-" + b"x" * (1024 * 1024))
    assert response.status_code == 413


def test_invalid_extension_is_rejected():
    client, _ = build_client()
    response = upload(client, filename="notes.txt", content=b"hello")
    assert response.status_code == 400


def test_magic_bytes_must_match_extension():
    client, _ = build_client()
    response = upload(client, filename="fake.pdf", content=b"\x89PNG\r\n\x1a\nsomething")
    assert response.status_code == 400


def test_valid_pdf_is_accepted_and_stored_under_upload_id():
    client, _ = build_client()
    response = upload(client)

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "PENDING"
    upload_id = payload["upload_id"]

    app = client.app
    storage = app.state.storage
    repo = app.state.repo
    assert f"uploads/{upload_id}/ticket.pdf" in storage.objects
    assert storage.objects[f"uploads/{upload_id}/ticket.pdf"] == (PDF, "application/pdf")
    assert repo.pending[upload_id] == "ticket.pdf"


def test_filename_is_sanitized_before_object_path():
    client, _ = build_client()
    response = upload(client, filename="../../evil name.pdf")

    assert response.status_code == 202
    upload_id = response.json()["upload_id"]
    paths = list(client.app.state.storage.objects)
    assert len(paths) == 1
    assert paths[0].startswith(f"uploads/{upload_id}/")
    assert ".." not in paths[0]
    assert " " not in paths[0]


def test_png_and_jpeg_are_accepted():
    client, _ = build_client()
    png = client.post(
        "/upload",
        data={"code": CODE},
        files={"file": ("receipt.png", b"\x89PNG\r\n\x1a\nrest", "image/png")},
    )
    jpeg = client.post(
        "/upload",
        data={"code": CODE},
        files={"file": ("receipt.jpg", b"\xff\xd8\xffrest", "image/jpeg")},
    )
    assert png.status_code == 202
    assert jpeg.status_code == 202


def test_rate_limit_rejects_after_limit():
    client, _ = build_client(rate_limit=2)
    assert upload(client).status_code == 202
    assert upload(client).status_code == 202
    assert upload(client).status_code == 429


def test_wrong_code_does_not_consume_rate_limit():
    client, _ = build_client(rate_limit=1)
    assert upload(client, code="wrong").status_code == 401
    assert upload(client).status_code == 202
    assert upload(client).status_code == 429


def test_unknown_status_is_404():
    client, _ = build_client()
    assert client.get("/status/unknown").status_code == 404


def test_status_returns_pending_without_result():
    client, _ = build_client()
    upload_id = upload(client).json()["upload_id"]
    response = client.get(f"/status/{upload_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "PENDING"
    assert "result" not in payload


def test_status_returns_failed_error_code():
    client, _ = build_client()
    repo = client.app.state.repo
    repo.statuses["u1"] = {
        "upload_id": "u1",
        "status": "FAILED",
        "error_code": "EXTRACTION_FAILED",
        "updated_at": None,
    }
    payload = client.get("/status/u1").json()
    assert payload["status"] == "FAILED"
    assert payload["error_code"] == "EXTRACTION_FAILED"


def test_status_returns_result_when_completed():
    client, _ = build_client()
    repo = client.app.state.repo
    repo.statuses["u1"] = {
        "upload_id": "u1",
        "status": "COMPLETED",
        "error_code": None,
        "updated_at": None,
    }
    repo.expenses["u1"] = {
        "expense_id": "e1",
        "rfc_emisor": "ABC010101AB1",
        "total": 46.40,
        "category": "FOOD",
        "expense_date": "2026-11-05",
        "policy_status": "VALID",
        "policy_reasons": [],
        "policy_details": {},
    }

    payload = client.get("/status/u1").json()

    assert payload["status"] == "COMPLETED"
    assert payload["result"]["policy_status"] == "VALID"
    assert payload["result"]["total"] == "46.40"
    assert payload["result"]["category"] == "FOOD"


def test_sanitize_filename_keeps_only_safe_characters():
    assert sanitize_filename("../../evil name.pdf") == "evil_name.pdf"
    assert sanitize_filename("Factura Noviembre.PDF") == "Factura_Noviembre.pdf"
    assert sanitize_filename("...") == "upload"


def test_rate_limiter_expires_old_events():
    now = [0.0]
    limiter = SlidingWindowRateLimiter(1, window_seconds=3600, clock=lambda: now[0])
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    now[0] = 3601.0
    assert limiter.allow("ip")


def test_limiter_uses_monotonic_clock_by_default():
    limiter = SlidingWindowRateLimiter(10)
    before = time.monotonic()
    assert limiter.allow("ip")
    assert limiter._clock() >= before
