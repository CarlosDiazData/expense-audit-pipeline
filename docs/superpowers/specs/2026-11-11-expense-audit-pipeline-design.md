# Expense Audit Pipeline — Design

- **Date:** 2026-11-11
- **Status:** Approved design, pending implementation plan
- **Repository:** `expense-audit-pipeline`
- **Cloud:** Google Cloud Platform (serverless)
- **Conversation language:** Spanish. Technical artifacts (this document, code, identifiers, tests) in English. Demo UI copy in Spanish (Mexican expense domain).

## 1. Purpose

Build a serverless, low-cost expense audit pipeline for a portfolio demo. An employee or provider uploads a receipt (PDF or image) through a small web page. The pipeline extracts structured data with an LLM, evaluates an explainable deterministic expense policy, and stores the result in BigQuery for later visualization.

The demo must be cheap to run (< $1 USD/month under light traffic), reproducible from Terraform, and legible as a portfolio artifact: event-driven architecture, least-privilege IAM, structured LLM output, deterministic business rules, and real tests.

## 2. Goals

- End-to-end event-driven flow: upload → GCS → Eventarc → Cloud Function Gen2 → Gemini Flash structured extraction → deterministic policy engine → BigQuery.
- Public demo UI protected by a shared access code, with live processing status and result feedback.
- Terraform-managed infrastructure, deployable from scratch with documented build and deploy steps.
- Deterministic, explainable policy evaluation stored as reason codes and details.
- Test suite covering the domain engine, adapters with fakes, and end-to-end manual verification.
- Total infrastructure cost under $1 USD/month with light demo traffic.

## 3. Non-goals (this phase)

- **Looker Studio dashboard and BigQuery views.** Deferred to a later visualization phase. Data model is designed so views and the dashboard can be added without pipeline changes.
- **Webhook or email alerting.** Deferred. Alerts are represented as `policy_status` values and reason codes; the future dashboard consumes them.
- Multi-tenancy, user accounts, or per-user authentication. A shared access code is the only gate.
- Production SLA, high availability, disaster recovery, or compliance certifications.
- OCR via Document AI. Gemini multimodal input covers PDFs and images directly.
- CI/CD deploy pipeline. Terraform and Make targets only; lint/test CI is optional.

## 4. Architecture

```
┌──────────────────────────────┐
│  Upload Web (Cloud Run)      │  FastAPI + HTML/JS
│  GET /  POST /upload         │  access code in Secret Manager
│  GET /status/{upload_id}     │
│  GET /healthz                │
└──────────────┬───────────────┘
               │ file upload (multipart, proxied)
               ▼
┌──────────────────────────────┐
│  GCS Landing Bucket          │  uploads/{upload_id}/{filename}
│  private, uniform access     │  lifecycle: delete after 90 days
└──────────────┬───────────────┘
               │ Eventarc: google.cloud.storage.object.v1.finalized
               │ filter: prefix uploads/
               ▼
┌──────────────────────────────┐
│  Cloud Function Gen2         │  Python 3.12, 512 MiB, 120 s timeout
│  process-ticket              │  1. idempotency + attempt guard
│                              │  2. Gemini Flash structured extraction
│                              │  3. deterministic validation
│                              │  4. policy engine
│                              │  5. BigQuery MERGE + status update
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│  BigQuery dataset            │  expenses (partitioned)
│  expense_audit               │  processing_status
│                              │  category_limits
└──────────────────────────────┘
               │
               ▼
   (deferred) Looker Studio dashboard
```

### 4.1 Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM | Gemini Flash via Vertex AI | Native GCP, multimodal (PDF/image), structured output, service-account auth without API keys. Cost is cents per demo run. |
| LLM auth | Service account (Vertex AI) | No API key secret to rotate; least-privilege IAM. |
| OCR | None | Gemini accepts PDFs and images directly; removes Document AI from scope. |
| Function flavor | Cloud Functions Gen2 | Native GCS event trigger via Eventarc, container-based, Python 3.12. |
| Upload transport | Proxied through Cloud Run | Centralized validation of access code, MIME, and size before touching GCS. 10 MB limit is sufficient for receipts. |
| Processing state | `processing_status` in BigQuery | Enables UI polling without Firestore; one data store for the demo. |
| Correlation | `upload_id` in object path and metadata | Traceability from upload through processing, storage, and query. |
| Partitioning | `expenses` partitioned by `DATE(created_at)` | Ingestion date is always present; `expense_date` can be missing or invalid. |
| Code layout | Hexagonal (`domain/`, `adapters/`, entrypoints) | Domain is testable without GCP; adapters swappable and fakeable. |
| Infra | Terraform (local state) | Reproducible, portfolio-grade IaC. Remote GCS backend documented as optional. |

### 4.2 Components

1. **Upload Web — Cloud Run (`app/upload`)**
   - FastAPI application serving one HTML page and three JSON endpoints.
   - Validates access code (constant-time comparison against Secret Manager value), file size (10 MB), and file type by extension plus magic bytes (`%PDF-`, PNG, JPEG signatures).
   - Generates `upload_id` (UUIDv4), uploads to `gs://{LANDING_BUCKET}/uploads/{upload_id}/{safe_filename}`, writes a `PENDING` row to `processing_status`, returns the `upload_id`.
   - Serves status polling from `processing_status` and, when `COMPLETED`, the corresponding row from `expenses`.
   - Config via environment variables: `GCP_PROJECT`, `LANDING_BUCKET`, `BQ_DATASET`, `ACCESS_CODE_SECRET`, `MAX_UPLOAD_MB`, `RATE_LIMIT_PER_HOUR`.

2. **Landing bucket (`terraform/storage.tf`)**
   - Uniform bucket-level access, public access prevention enforced, no public objects.
   - Object path: `uploads/{upload_id}/{filename}`.
   - Lifecycle rule: delete objects after 90 days.

3. **Cloud Function Gen2 (`app/processor`)**
   - Entry point receives the Eventarc CloudEvent (bucket, object name, size, content type, metadata).
   - Steps:
     1. Read or create `processing_status`; if `COMPLETED`, return success (idempotency). If `attempts >= 5`, mark `FAILED` with `RETRY_EXHAUSTED` and return success to stop Eventarc retries.
     2. Set `PROCESSING`, increment `attempts`.
     3. Download object into memory (reject > 10 MB).
     4. Call Gemini Flash with the Pydantic response schema.
     5. Run deterministic validation and policy evaluation.
     6. `MERGE` the expense row on `source_object`.
     7. Set `COMPLETED` (or `FAILED` with an error code) and `updated_at`.
   - Document-level failures are recorded and swallowed (return success) so Eventarc does not retry forever. Transient infrastructure failures raise, allowing Eventarc retries.
   - Runtime config: Gen2, Python 3.12, 512 MiB, 120 s timeout, min instances 0, max instances 5.
   - Environment: `GCP_PROJECT`, `BQ_DATASET`, `GEMINI_MODEL` (default `gemini-2.5-flash`), `GEMINI_LOCATION` (`us-central1`), `COMPANY_RFC` (optional), `GCS_ALLOWED_BUCKET`.

4. **BigQuery (`terraform/bigquery.tf`)**
   - Dataset `expense_audit` in `us-central1`.
   - Tables described in section 5.
   - No views in this phase; views belong to the deferred visualization phase.

5. **Looker Studio (deferred)**
   - Not implemented. Future work connects to `expenses` and derives alert and budget views.

## 5. Data model

### 5.1 `expenses`

| Column | Type | Notes |
|---|---|---|
| `expense_id` | STRING | UUIDv4, primary identifier |
| `upload_id` | STRING | Links to `processing_status` |
| `source_object` | STRING | `gs://bucket/object`; logical unique key for idempotency |
| `original_filename` | STRING | As uploaded |
| `rfc_emisor` | STRING | Normalized uppercase, null if absent |
| `rfc_receptor` | STRING | Normalized uppercase, null if absent |
| `expense_date` | DATE | Null if absent or unparseable |
| `subtotal` | NUMERIC(12,2) | Null if absent |
| `iva` | NUMERIC(12,2) | Null if absent |
| `total` | NUMERIC(12,2) | Null if absent |
| `currency` | STRING | ISO 4217, default `MXN` |
| `category` | STRING | `FOOD`, `TRANSPORT`, `SOFTWARE`, `LODGING`, `OTHER` |
| `vendor_name` | STRING | Null if absent |
| `description` | STRING | Short description, null if absent |
| `policy_status` | STRING | `VALID`, `SUSPICIOUS`, `NON_DEDUCTIBLE` |
| `policy_reasons` | ARRAY<STRING> | Reason codes, see section 6 |
| `policy_details` | JSON | Machine-readable details per reason |
| `llm_model` | STRING | Model identifier used |
| `llm_raw_response` | JSON | Raw structured response for debugging |
| `created_at` | TIMESTAMP | Ingestion time |
| `processed_at` | TIMESTAMP | End of processing |

- Partitioned by `DATE(created_at)`.
- Clustered by `policy_status`, `category`.

All writes use DML (`INSERT`/`MERGE`), never streaming inserts, so reads from the status endpoint are immediately consistent.

### 5.2 `processing_status`

| Column | Type | Notes |
|---|---|---|
| `upload_id` | STRING | Primary identifier |
| `original_filename` | STRING | As uploaded |
| `status` | STRING | `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `attempts` | INT64 | Incremented per function invocation; bounded at 5 |
| `error_code` | STRING | Machine-readable failure code |
| `error_message` | STRING | Sanitized message, no document content |
| `created_at` | TIMESTAMP | Upload time |
| `updated_at` | TIMESTAMP | Last state change |

- Partitioned by `DATE(created_at)`, clustered by `status`.

### 5.3 `category_limits`

| Column | Type | Notes |
|---|---|---|
| `category` | STRING | One of the five categories |
| `per_expense_limit` | NUMERIC(12,2) | Max allowed per single expense |
| `monthly_limit` | NUMERIC(12,2) | Max allowed per calendar month |
| `currency` | STRING | `MXN` |
| `active` | BOOL | Allows disabling a rule without deleting it |

Seed data:

| Category | Per expense (MXN) | Monthly (MXN) |
|---|---|---|
| `FOOD` | 50 | 500 |
| `TRANSPORT` | 200 | 2000 |
| `SOFTWARE` | 500 | 3000 |
| `LODGING` | 300 | 3000 |
| `OTHER` | 100 | 1000 |

## 6. Extraction and policy engine

### 6.1 Extraction schema (Pydantic)

```python
class Category(str, Enum):
    FOOD = "FOOD"
    TRANSPORT = "TRANSPORT"
    SOFTWARE = "SOFTWARE"
    LODGING = "LODGING"
    OTHER = "OTHER"

class ExtractedExpense(BaseModel):
    rfc_emisor: str | None
    rfc_receptor: str | None
    expense_date: date | None
    subtotal: Decimal | None
    iva: Decimal | None
    total: Decimal | None
    currency: str = "MXN"
    category: Category
    vendor_name: str | None
    description: str | None
```

- Gemini is called with `response_mime_type="application/json"` and `response_schema=ExtractedExpense`.
- Prompt rules: extract only what the document states; return null when absent; never invent values; choose `OTHER` when the category is unclear; currency ISO 4217 defaulting to MXN.

### 6.2 Deterministic validation

- RFC normalization: strip spaces, uppercase. Regex: `^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$`.
- Totals tolerance: `abs(subtotal + iva - total) <= 1.00` MXN.
- Future dates are flagged (`DATE_IN_FUTURE`), not rejected.
- Required fields for a full record: RFC emisor, RFC receptor, expense date, total.
- Negative or zero total is flagged as `INVALID_AMOUNT`.

### 6.3 Policy reason codes and precedence

Non-deductible findings:

| Code | Rule |
|---|---|
| `INVALID_RFC` | Emisor or receptor RFC fails the regex |
| `NON_DEDUCTIBLE_CATEGORY` | Category is absent from active `category_limits` |
| `RECEPTOR_NOT_COMPANY` | `COMPANY_RFC` is configured and receptor differs |
| `MISSING_CRITICAL_FIELDS` | Any required field is null |

Suspicious findings:

| Code | Rule |
|---|---|
| `TOTAL_MISMATCH` | `abs(subtotal + iva - total) > 1.00` |
| `DATE_IN_FUTURE` | `expense_date` is after processing date |
| `INVALID_AMOUNT` | Total is negative or zero |
| `PER_EXPENSE_LIMIT_EXCEEDED` | `total > per_expense_limit` for the category |
| `MONTHLY_BUDGET_EXCEEDED` | Month total for the category plus this expense exceeds `monthly_limit` |
| `DUPLICATE_EXPENSE` | Another `expenses` row has the same `rfc_emisor`, `total`, and `expense_date` with a different `upload_id` |
| `CURRENCY_UNSUPPORTED` | Currency is not `MXN`; limit rules are skipped for the expense |

Precedence: any non-deductible finding ⇒ `NON_DEDUCTIBLE`; else any suspicious finding ⇒ `SUSPICIOUS`; else `VALID`.

The LLM does not decide policy. It extracts; rules decide. Every finding records a code plus detail in `policy_details` (for example the exceeded limit and observed amount, or the duplicate `expense_id`).

Monthly budget evaluation sums `total` for the same category and calendar month from `expenses` where `policy_status != 'NON_DEDUCTIBLE'`, then adds the current expense.

Duplicate detection is exact on `(rfc_emisor, total, expense_date)`. Extraction variance handling is out of scope.

## 7. Processing flow and error handling

### 7.1 Upload API

| Endpoint | Behavior |
|---|---|
| `GET /` | HTML page with access code field, drag-and-drop area, result card |
| `POST /upload` | Multipart `code` + `file`. `401` wrong code, `429` rate limited, `413` oversized, `400` invalid type. Success: `202` with `{upload_id, status: "PENDING"}` |
| `GET /status/{upload_id}` | `{upload_id, status, error_code?, result?}`. `result` includes `policy_status`, `policy_reasons`, `rfc_emisor`, `total`, `category`, `expense_date` |
| `GET /healthz` | `{"status": "ok"}` |

Rate limiting: in-memory token bucket per instance, 10 uploads/hour per client IP. Best effort, documented as non-distributed; Cloud Armor is future work.

### 7.2 Failure matrix

| Failure | Handling |
|---|---|
| Invalid file type or size | Rejected at upload with `400`/`413`; nothing reaches GCS |
| Gemini transient error | 3 internal attempts with exponential backoff; then `FAILED` with `EXTRACTION_FAILED` |
| Encrypted or unreadable document | `FAILED` with `UNSUPPORTED_DOCUMENT`; no `expenses` row |
| Schema-invalid extraction | `FAILED` with `EXTRACTION_FAILED` |
| BigQuery or GCS transient failure | Function raises; Eventarc retries; idempotent `MERGE` |
| Duplicate Eventarc delivery | `MERGE` on `source_object` and `COMPLETED` short-circuit |
| Retry storm | `attempts >= 5` ⇒ `FAILED` with `RETRY_EXHAUSTED`, return success |
| Stuck `PROCESSING` | UI treats > 5 minutes as timeout and shows a soft error |

Logs are structured, include `upload_id` and `source_object`, and never include document content or RFCs.

## 8. Security

- Access code provided through a sensitive Terraform variable, minimum 12 characters, stored in Secret Manager. Compared with `secrets.compare_digest`.
- Two service accounts, least privilege:
  - `sa-uploader`: `roles/storage.objectCreator` on the landing bucket, `roles/secretmanager.secretAccessor` on the access-code secret, `roles/bigquery.dataEditor` on the dataset (writes `PENDING` status rows).
  - `sa-processor`: `roles/storage.objectViewer` on the bucket, `roles/bigquery.dataEditor` on the dataset, `roles/aiplatform.user`.
  - Eventarc trigger identity: `sa-processor` with `roles/eventarc.eventReceiver`.
- Bucket: public access prevention, uniform access, no public objects.
- No API keys in the codebase; Vertex AI authenticates via service account.
- Input validation: extension plus magic bytes, 10 MB cap, filename sanitization before building the object path.
- `terraform.tfvars` and state files ignored by git; secrets are never committed.
- Logs exclude document content and RFCs.

## 9. Testing strategy

- **Unit (pure domain):** every policy reason code, precedence resolution, RFC validation, totals tolerance boundaries, future-date rule, duplicate rule, monthly budget accumulation.
- **Adapter tests with fakes:** Gemini response parsing (recorded fixture, no live calls), BigQuery MERGE SQL construction, GCS object path building, upload validation.
- **Function integration:** simulated Eventarc payload with fake adapters; asserts idempotency (same event twice ⇒ one row) and status transitions.
- **Upload service:** wrong code ⇒ `401`, oversized ⇒ `413`, invalid type ⇒ `400`, valid PDF ⇒ `202` and object created in a fake GCS.
- **Fixtures:** six synthetic PDF invoices generated with reportlab — valid, over per-expense limit, duplicate pair (two files), non-deductible category, and a noisy "scanned" variant. Committed under `samples/`.
- **End-to-end (manual):** `scripts/e2e_demo.sh` uploads the samples against deployed infrastructure and queries BigQuery for expected statuses.
- **Static checks:** `ruff check` and `pytest`. Optional GitHub Actions workflow running lint and tests only (no deploy).

## 10. Repository layout

```
expense-audit-pipeline/
├── app/
│   ├── upload/              # FastAPI Cloud Run service
│   │   ├── main.py
│   │   ├── templates/
│   │   └── static/
│   └── processor/           # Cloud Function entrypoint
│       └── main.py
├── src/expense_audit/
│   ├── domain/              # models, validation, policy engine (pure)
│   ├── adapters/            # gemini, bigquery, gcs, secrets
│   └── config.py
├── infra/                   # Terraform
│   ├── versions.tf
│   ├── variables.tf
│   ├── apis.tf
│   ├── storage.tf
│   ├── bigquery.tf
│   ├── cloud_run.tf
│   ├── cloud_function.tf
│   ├── secrets.tf
│   ├── iam.tf
│   └── outputs.tf
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── samples/                 # synthetic invoice PDFs
├── scripts/
│   ├── generate_samples.py
│   └── e2e_demo.sh
├── docs/superpowers/specs/  # this document
├── pyproject.toml
├── Makefile                 # build, deploy, test, lint
└── README.md
```

Build and deploy split:

- `make build` builds and pushes the Cloud Run image to Artifact Registry and assembles the function source directory with the shared package.
- `make deploy` runs `terraform apply` with the image tag and function source path.
- Terraform provisions infrastructure only; it does not build images.

## 11. Infrastructure (Terraform)

| File | Resources |
|---|---|
| `apis.tf` | Enable Cloud Run, Cloud Functions, Eventarc, BigQuery, Artifact Registry, Vertex AI, Secret Manager, IAM |
| `storage.tf` | Landing bucket, lifecycle rule, IAM |
| `bigquery.tf` | Dataset and the three tables with partitioning and clustering |
| `cloud_run.tf` | Upload service, service account, env vars, public invoker |
| `cloud_function.tf` | Gen2 function, source, runtime config, env vars, event trigger with retry policy |
| `secrets.tf` | Secret Manager secret and version for the access code |
| `iam.tf` | Service accounts and least-privilege bindings |
| `variables.tf` | `project_id`, `region` (default `us-central1`), `company_rfc`, `gemini_model`, `access_code`, `max_upload_mb` |
| `outputs.tf` | Cloud Run URL, bucket name, dataset name |

- State: local by default; a commented GCS backend example is included for remote state.
- `terraform.tfvars.example` documents required values.
- Recommended manual step: GCP budget alert at $5 USD (billing budgets need a billing account ID, documented in README).

## 12. Demo UX

1. Open the Cloud Run URL.
2. Enter the access code.
3. Drag and drop a receipt (PDF, PNG, JPEG).
4. Page shows `Procesando...` and polls `/status/{upload_id}` every 2 seconds.
5. On completion, render a result card: RFC emisor, total, category, and a badge — `VÁLIDO`, `SOSPECHOSO`, `NO DEDUCIBLE` — with the reasons translated to Spanish.
6. On failure, show a clear error message with the error code.

UI copy is Spanish. Identifiers, code, tests, and documentation are English.

## 13. Cost estimate

| Service | Usage assumption | Estimated cost |
|---|---|---|
| Cloud Run | Few hundred requests/month | $0 (free tier) |
| Cloud Functions Gen2 | Few hundred invocations/month | $0 (free tier) |
| GCS | < 1 GB standard | $0 (free tier) |
| BigQuery | < 10 GB storage, < 1 TB queries/month | $0 (free tier) |
| Artifact Registry | One small image | ~$0.01 |
| Vertex AI Gemini Flash | Tens of receipts, cents each | < $0.05 |
| **Total** | | **< $1 USD/month** |

## 14. Assumptions and risks

- Synthetic invoices are clean enough for reliable extraction; one noisy sample covers degraded input. Real-world accuracy is not guaranteed.
- Demo invoices are MXN. Non-MXN expenses are flagged `CURRENCY_UNSUPPORTED` and skip amount-limit rules; no currency conversion is implemented.
- Vertex AI Gemini Flash is available in `us-central1` for the project used.
- Eventarc retries can last up to 24 hours; the `attempts >= 5` guard bounds retry storms.
- In-memory rate limiting is per instance and therefore approximate.
- Deferred visualization means the demo's final "wow" is the result card plus BigQuery console, not a dashboard yet.
- Terraform local state is acceptable for a single-user demo; remote state is documented but optional.

## 15. Acceptance criteria

- Uploading a valid sample invoice through the web page ends with `processing_status = COMPLETED` and an `expenses` row with the expected `policy_status`.
- The six samples produce: one `VALID`, one `SUSPICIOUS` for per-expense limit, one `SUSPICIOUS` for duplicate, one `NON_DEDUCTIBLE`, and a controlled outcome for the noisy sample.
- Reprocessing the same object does not create a second `expenses` row.
- Wrong access code, oversized file, and invalid type are rejected with `401`, `413`, and `400` respectively.
- `pytest` and `ruff check` pass locally.
- `terraform validate` and `terraform plan` succeed with a filled `terraform.tfvars`.
- README documents prerequisites, setup, build, deploy, demo flow, and cost controls.
