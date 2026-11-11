# Expense Audit Pipeline

Serverless expense audit demo on Google Cloud Platform. An employee or provider uploads a
receipt (PDF, PNG, or JPEG); the pipeline extracts structured data with Gemini Flash, applies a
deterministic and explainable expense policy, and stores the result in BigQuery.

The design rationale lives in
[`docs/superpowers/specs/2026-11-11-expense-audit-pipeline-design.md`](docs/superpowers/specs/2026-11-11-expense-audit-pipeline-design.md).

## Architecture

```
Upload web (Cloud Run, FastAPI)
        │  POST /upload  (access code + file validation)
        ▼
GCS landing bucket  gs://…/uploads/{upload_id}/{filename}
        │  Eventarc: google.cloud.storage.object.v1.finalized (prefix uploads/)
        ▼
Cloud Function Gen2  process_ticket
  1. idempotency + attempt guard
  2. Gemini Flash structured extraction
  3. deterministic validation + policy engine
  4. BigQuery MERGE + status update
        ▼
BigQuery dataset expense_audit
  expenses · processing_status · category_limits
```

- Extraction is the only LLM step. Policy decisions come from deterministic rules with reason
  codes, so every `VALID`, `SUSPICIOUS`, or `NON_DEDUCTIBLE` outcome is explainable.
- All writes use DML (`INSERT`/`MERGE`), so the status endpoint reads immediately consistent data.
- The Looker Studio dashboard is intentionally deferred; the result card and BigQuery console are
  the demo surface for this phase.

## Repository layout

```
app/upload/          FastAPI upload service, templates, static assets, Dockerfile
app/processor/       Cloud Function Gen2 entrypoint
src/expense_audit/   domain (pure rules), adapters (Gemini, BigQuery, GCS, Secret Manager)
tests/               unit and integration tests with in-memory fakes
infra/               Terraform
samples/             six synthetic invoice PDFs
scripts/             sample generator and e2e demo script
```

## Prerequisites

- Python 3.12+
- Terraform 1.6+
- Docker
- `gcloud` authenticated with a project that has billing enabled
- A GCP project with permission to enable APIs and create service accounts

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
gcloud auth configure-docker us-central1-docker.pkg.dev
```

## Local setup

```bash
make install     # creates .venv and installs the package with dev extras
make test        # pytest
make lint        # ruff check + format check
make samples     # regenerates the synthetic PDFs
```

Environment variables used by the services:

| Variable | Service | Default | Purpose |
|---|---|---|---|
| `GCP_PROJECT` | both | — | Project ID |
| `LANDING_BUCKET` | upload | — | GCS landing bucket |
| `BQ_DATASET` | both | `expense_audit` | BigQuery dataset |
| `ACCESS_CODE_SECRET` | upload | `expense-audit-access-code` | Secret Manager secret ID |
| `MAX_UPLOAD_MB` | both | `10` | Upload and download size cap |
| `RATE_LIMIT_PER_HOUR` | upload | `10` | Best-effort uploads per IP per instance |
| `GEMINI_MODEL` | processor | `gemini-2.5-flash` | Vertex AI model |
| `GEMINI_LOCATION` | processor | `us-central1` | Vertex AI location |
| `COMPANY_RFC` | processor | empty | Enables `RECEPTOR_NOT_COMPANY` when set |
| `GCS_ALLOWED_BUCKET` | processor | `LANDING_BUCKET` | Bucket accepted by the trigger |
| `MAX_ATTEMPTS` | processor | `5` | Retry guard before `RETRY_EXHAUSTED` |

## Deploy

1. Create the Terraform variables and deploy the Artifact Registry repository first (the image does
   not exist yet, so a full apply would fail on Cloud Run):

   ```bash
   cp infra/terraform.tfvars.example infra/terraform.tfvars
   # edit project_id, access_code, and optionally company_rfc
   terraform -chdir=infra init
   terraform -chdir=infra apply -target=google_artifact_registry_repository.upload \
     -var-file=terraform.tfvars
   ```

2. Build and push the upload image, and assemble the Cloud Function source:

   ```bash
   make build
   ```

3. Apply the full stack:

   ```bash
   make deploy
   ```

4. Read the outputs:

   ```bash
   terraform -chdir=infra output
   terraform -chdir=infra output -raw upload_url
   ```

`terraform apply` also seeds `category_limits` with a MERGE job, so re-applies are idempotent.

## Demo flow

1. Open the `upload_url` from the Terraform output.
2. Enter the access code from `terraform.tfvars`.
3. Upload one of the files in `samples/`.
4. The page polls `/status/{upload_id}` every two seconds and renders a result card with a
   `VÁLIDO`, `SOSPECHOSO`, or `NO DEDUCIBLE` badge and the translated reason codes.

Run the full sample sweep against the deployed stack:

```bash
UPLOAD_URL="$(terraform -chdir=infra output -raw upload_url)" \
ACCESS_CODE="your-demo-access-code" \
PROJECT_ID="your-project-id" BQ_DATASET="expense_audit" \
make e2e
```

Expected outcomes are documented in [`samples/README.md`](samples/README.md). The noisy sample is
a controlled variant: the script accepts either a completed extraction or `EXTRACTION_FAILED`.

## Policy rules

Non-deductible: `INVALID_RFC`, `NON_DEDUCTIBLE_CATEGORY`, `RECEPTOR_NOT_COMPANY`,
`MISSING_CRITICAL_FIELDS`.

Suspicious: `TOTAL_MISMATCH`, `DATE_IN_FUTURE`, `INVALID_AMOUNT`, `PER_EXPENSE_LIMIT_EXCEEDED`,
`MONTHLY_BUDGET_EXCEEDED`, `DUPLICATE_EXPENSE`, `CURRENCY_UNSUPPORTED`.

Precedence: any non-deductible finding wins; otherwise any suspicious finding; otherwise valid.
Limits come from `category_limits` (FOOD 50/500, TRANSPORT 200/2000, SOFTWARE 500/3000,
LODGING 300/3000, OTHER 100/1000 MXN per expense/month). Non-MXN expenses skip amount rules.

## Data model

- `expenses`: one row per `source_object`, partitioned by `DATE(created_at)` and clustered by
  `policy_status, category`.
- `processing_status`: `PENDING → PROCESSING → COMPLETED | FAILED`, with `attempts` capped at 5.
- `category_limits`: active policy limits, seeded by Terraform.

## Cost controls

- Cloud Run and Cloud Functions scale to zero; BigQuery and GCS stay in free-tier usage.
- Landing objects expire after 90 days.
- Recommended: create a GCP budget alert at $5 USD. Budgets require a billing account ID:
  `gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID ...` (see
  `gcloud billing budgets create --help`).

## Security

- Shared access code in Secret Manager, compared with `secrets.compare_digest`.
- Two least-privilege service accounts: `sa-uploader` (object create, dataset editor, secret access)
  and `sa-processor` (object view, dataset editor, Vertex AI user, Eventarc receiver).
- Buckets enforce uniform access and public access prevention; objects are never public.
- Uploads validate extension plus magic bytes, sanitize the filename, and cap size at 10 MB.
- Logs and `error_message` values never include document content or RFCs.

## Testing

```bash
make test
make lint
terraform -chdir=infra validate
terraform -chdir=infra fmt -check -recursive
```

Unit tests cover validation boundaries and every policy reason. Integration tests use in-memory
fakes for GCS, BigQuery, Gemini, and Secret Manager, and cover processor idempotency, retry
exhaustion, failure swallowing vs. infrastructure retries, and upload `401`/`413`/`400`/`202`.

## Troubleshooting

- **Cloud Run revision fails to start**: confirm `make build` pushed the image and that
  `upload_image` points to it.
- **Function never triggers**: check the Eventarc trigger filters (`bucket` and `uploads/*`) and
  that the processor service account has `roles/eventarc.eventReceiver`.
- **`EXTRACTION_FAILED` repeatedly**: confirm the Vertex AI API is enabled and the model is
  available in the configured region.
- **`terraform plan` fails on the function source**: run `make build` before `terraform apply`.
- **No rows in BigQuery**: check `processing_status.error_code` and Cloud Function logs; document
  failures are recorded there instead of retrying forever.

## Deferred work

Looker Studio views and alerts, email/webhook notifications, and multi-user authentication are out
of scope for this phase. The data model already supports them without pipeline changes.
