# Feature: Expense Audit Pipeline (GCP serverless)

Branch: `feat/expense-audit-pipeline` | Delivery: `ask-on-risk` | Test runner: `pytest` (`.venv/bin/pytest`)

Source of truth for requirements: `docs/superpowers/specs/2026-11-11-expense-audit-pipeline-design.md` (approved design).

## Specs

- **S1** End-to-end event-driven flow: upload → GCS `uploads/{upload_id}/{filename}` → Eventarc `google.cloud.storage.object.v1.finalized` → Cloud Function Gen2 → Gemini Flash structured extraction → deterministic policy engine → BigQuery.
- **S2** Upload web: FastAPI on Cloud Run with `GET /`, `POST /upload`, `GET /status/{upload_id}`, `GET /healthz`.
- **S3** `POST /upload` responses: `401` wrong access code, `429` rate limited, `413` oversized (10 MB), `400` invalid type; success `202` with `{upload_id, status: "PENDING"}`.
- **S4** Access code compared with `secrets.compare_digest` against Secret Manager; file type validated by extension plus magic bytes (`%PDF-`, PNG, JPEG); filename sanitized before the object path.
- **S5** `processing_status` states `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`; `attempts` bounded at 5; retry exhaustion marks `FAILED` with `RETRY_EXHAUSTED` and returns success.
- **S6** `expenses` row keyed by `source_object`; idempotent `MERGE`; reprocessing the same object creates no second row.
- **S7** Extraction schema `ExtractedExpense` exactly as design section 6.1: `rfc_emisor`, `rfc_receptor`, `expense_date`, `subtotal`, `iva`, `total`, `currency` (default `MXN`), `category`, `vendor_name`, `description`.
- **S8** Gemini called with `response_mime_type="application/json"` and `response_schema=ExtractedExpense`; prompt extracts only stated values, returns null when absent, never invents, uses `OTHER` when category is unclear.
- **S9** RFC normalization: strip spaces, uppercase; regex `^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$`.
- **S10** Totals tolerance `abs(subtotal + iva - total) <= 1.00` MXN; future dates flagged `DATE_IN_FUTURE`; required fields RFC emisor, RFC receptor, expense date, total; negative/zero total flagged `INVALID_AMOUNT`.
- **S11** Non-deductible codes: `INVALID_RFC`, `NON_DEDUCTIBLE_CATEGORY`, `RECEPTOR_NOT_COMPANY`, `MISSING_CRITICAL_FIELDS`.
- **S12** Suspicious codes: `TOTAL_MISMATCH`, `DATE_IN_FUTURE`, `INVALID_AMOUNT`, `PER_EXPENSE_LIMIT_EXCEEDED`, `MONTHLY_BUDGET_EXCEEDED`, `DUPLICATE_EXPENSE`, `CURRENCY_UNSUPPORTED`.
- **S13** Precedence: any non-deductible finding ⇒ `NON_DEDUCTIBLE`; else any suspicious finding ⇒ `SUSPICIOUS`; else `VALID`. Every finding records a code plus detail in `policy_details`.
- **S14** Monthly budget sums `total` for same category and calendar month from `expenses` where `policy_status != 'NON_DEDUCTIBLE'`, then adds the current expense.
- **S15** Duplicate detection exact on `(rfc_emisor, total, expense_date)` with a different `upload_id`.
- **S16** `CURRENCY_UNSUPPORTED` when currency is not `MXN`; per-expense and monthly limit rules are skipped for that expense.
- **S17** Failure matrix: invalid type/size rejected at upload; Gemini transient error retried 3 times then `FAILED`/`EXTRACTION_FAILED`; unreadable document `FAILED`/`UNSUPPORTED_DOCUMENT`; schema-invalid `FAILED`/`EXTRACTION_FAILED`; BigQuery/GCS transient failure raises so Eventarc retries; duplicate delivery short-circuits on `COMPLETED`.
- **S18** BigQuery tables `expenses` (partitioned by `DATE(created_at)`, clustered by `policy_status, category`), `processing_status` (partitioned by `DATE(created_at)`, clustered by `status`), `category_limits` with seed rows: FOOD 50/500, TRANSPORT 200/2000, SOFTWARE 500/3000, LODGING 300/3000, OTHER 100/1000 (MXN).
- **S19** Terraform (local state, optional GCS backend) provisions APIs, bucket with 90-day lifecycle and public-access prevention, dataset/tables, Cloud Run, Cloud Function Gen2 (512 MiB, 120 s, max 5), secret, least-privilege SAs, outputs.
- **S20** Tests: unit policy/validation, adapter tests with fakes, processor integration with fakes (idempotency and status transitions), upload service tests (`401`/`413`/`400`/`202`), six synthetic PDF samples, `scripts/e2e_demo.sh`, `ruff check`/`pytest`, README.
- **S21** Demo UX in Spanish: access code, drag-and-drop, `Procesando...` polling every 2 s, result card with badge `VÁLIDO`/`SOSPECHOSO`/`NO DEDUCIBLE`, clear failure message.

Assumptions (from design section 14): MXN demo invoices; no currency conversion; Vertex AI Gemini Flash in `us-central1`; in-memory rate limiting is best effort; visualization deferred.

## Tasks

- **T1** Scaffold project: `pyproject.toml`, package skeleton, config, Makefile base, tooling. Route: inline. Done, commit `3384eb8`.
- **T2** Domain models, validation, and policy engine with unit tests (S7, S9-S16). Route: inline. Done, commit `2679b95`.
- **T3** Adapters: Gemini, BigQuery, GCS, Secret Manager with fake-based tests (S6, S8, S17, S18). Route: inline. Done, commit `1943f4a`.
- **T4** Processor orchestration + Cloud Function entrypoint with integration tests (S1, S5, S6, S17). Route: inline. Done, commit `ec46e94`.
- **T5** Upload web service, HTML/JS UI, tests (S2-S4, S21). Route: inline. Done, commit `b419163`.
- **T6** Terraform infrastructure and seed (S19, S18). Route: inline. Done, commit `ff00929`.
- **T7** Sample generator, six synthetic PDFs, e2e script (S20). Route: inline. Done, commit `c9b876a`.
- **T8** README, final Makefile, CI workflow, final checks (S20). Route: inline. Done, commit `70085ba`.

## Log

- **L1 (2026-11-11, verbatim):** "continua el proyecto donde lo dejaste"
- Context: previous session ended after committing the approved design spec (`36bb7d1`). No implementation files existed and Engram had no observations. Resume point = implement the approved design.
- **L2 (2026-11-11):** Implementation strategy: hexagonal layout from design section 10, tests written first per task where runnable, work-unit commits per task. Terraform validated with `terraform validate`/`fmt -check`.
- Evidence: branch `feat/expense-audit-pipeline` created from `master` at `36bb7d1`.

- **L3 (2026-11-11):** Implemented T1-T7 inline. No Writer trigger held: no parallel independent units and the parent context stayed bounded, so no delegated writer was launched. Tests were written before each unit; RED was observed for the domain (missing modules), and adapter tests initially exposed BigQuery DATE parameter normalization (fixed by asserting the normalized `date` value).
- **L4 (2026-11-11):** Verification evidence observed locally: `pytest` 88 passed; `ruff check` clean; `ruff format --check` 28 files formatted; `terraform validate` success; `terraform fmt -check -recursive` clean. Not run: Docker image build and live GCP deploy (no image push or cloud mutation was authorized in this session).
- **L5 (2026-11-11):** Delivery forecast: 4743 authored changed lines across 7 work-unit commits, above the ~400-line review budget. Delivery strategy is `ask-on-risk`; PR slicing/chain strategy remains a user decision. No push and no PR were performed.
- **Risk:** item 2 (access code, Secret Manager, least-privilege IAM), item 5 (Terraform deploy, dependencies, installers), item 6 (live GCP behavior is not covered by local tests).
- **L6 (2026-11-11):** Independent verification (whole feature, baseline `36bb7d1`) found 2 blockers: (B1) the GCS adapter converted transient read errors into `DocumentError`, preventing Eventarc retries; (B2) the monthly budget double-counted the current expense on retry after a successful MERGE followed by a failed status update. Both were corrected with regression tests `tests/unit/test_gcs_transient.py` and `tests/integration/test_processor_retry.py`.
- **L7 (2026-11-11):** The correction batch also changed the Eventarc path pattern to `uploads/**` (single `*` matches one segment per Eventarc path patterns), made the e2e script require terminal states and assert expected policy/reasons, preserved the raw uploaded filename while sanitizing only the object path, aligned `ExtractedExpense` with required-nullable design fields, rejected encrypted PDFs as `UNSUPPORTED_DOCUMENT`, added `upload_id` object metadata plus JSON logs, and untracked the unrelated `.atl/` cache.
- **L8 (2026-11-11):** Post-correction evidence: `pytest` 92 passed; `ruff check` clean; `ruff format --check` 30 files; `terraform validate` success; `terraform fmt -check` clean; `bash -n scripts/e2e_demo.sh` OK. Still not run: Docker build and live GCP deploy/e2e.
- **L9 (2026-11-11):** Native review attempted on the correction slice (`70085ba..dfe6d99`) after the full base-diff exceeded the reviewer context budget (`lens_context_budget_exceeded`). Reliability and readability lenses were admitted; risk and resilience produced empty OpenCode task output across repeated grouped launches, so those slots were recorded unachievable and the transaction ended with native stop `unachievable_lens_slot`. No review acknowledgement or approval exists; delivery remains under ordinary repository policy.
- **L10 (2026-11-11):** First live apply showed Eventarc rejects the `name`/`match-path-pattern` filter on direct Cloud Storage triggers (`attribute name not found within event type`). The Terraform trigger now filters only by bucket; the processor's `uploads/` prefix guard remains authoritative. README updated.
- **L11 (2026-11-11):** Cloud Run reserves `/healthz` at the Google Frontend and returns its own 404 before the request reaches the container. Added `GET /health` as the externally reachable health endpoint and kept `/healthz` as a local alias; updated the upload test.
