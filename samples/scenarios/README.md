# Scenario invoices

Synthetic invoices that exercise every policy reason code not covered by the six core
samples. Generate them with `make samples` (or `python scripts/generate_samples.py
--scenarios-only`).

All expectations assume `company_rfc = "XYZ010101XY2"` (the deployed demo value). If the
company RFC is different, valid invoices whose receptor is `XYZ010101XY2` become
`NON_DEDUCTIBLE` with `RECEPTOR_NOT_COMPANY`.

## Independent scenarios

Upload these in any order; each one is self-contained.

| File | Expected status | Expected reasons / notes |
|---|---|---|
| `01_total_mismatch.pdf` | `SUSPICIOUS` | `TOTAL_MISMATCH` (100 + 16 != 120) |
| `02_future_date.pdf` | `SUSPICIOUS` | `DATE_IN_FUTURE` (date 2035-12-31) |
| `03_invalid_amount.pdf` | `SUSPICIOUS` | `INVALID_AMOUNT` (credit note, total -50) |
| `04_currency_usd.pdf` | `SUSPICIOUS` | `CURRENCY_UNSUPPORTED`; amount limits are skipped |
| `05_receptor_other.pdf` | `NON_DEDUCTIBLE` | `RECEPTOR_NOT_COMPANY` (receptor `ABC010101AB1`) |
| `06_missing_fields.pdf` | `NON_DEDUCTIBLE` | `MISSING_CRITICAL_FIELDS` (no receptor, no date) |
| `07_tolerance_exact.pdf` | `VALID` | Difference is exactly 1.00 and is accepted |
| `08_tolerance_mismatch.pdf` | `SUSPICIOUS` | `TOTAL_MISMATCH` (difference 1.01) |
| `09_valid_lodging.pdf` | `VALID` | LODGING 250, under the 300 per-expense limit |
| `10_valid_software.pdf` | `VALID` | SOFTWARE 300, under the 500 per-expense limit |
| `11_valid_transport.pdf` | `VALID` | TRANSPORT 150, under the 200 per-expense limit |
| `12_valid_other.pdf` | `VALID` | OTHER 80, under the 100 per-expense limit |
| `13_iva_missing.pdf` | `VALID` | IVA is absent, so the totals rule is skipped |

## Monthly budget

Files under `monthly_budget/` must be uploaded in filename order on a **clean**
`expenses` table:

1. `01_software_500_a.pdf` through `06_software_500_f.pdf` are each exactly the
   SOFTWARE per-expense limit (500), so they are `VALID` and accumulate 3,000.
2. `07_software_100_over_budget.pdf` adds 100 to the month; 3,000 + 100 exceeds the
   3,000 monthly limit and produces `SUSPICIOUS` with `MONTHLY_BUDGET_EXCEEDED`.

```bash
bq query --use_legacy_sql=false \
  'TRUNCATE TABLE `YOUR_PROJECT.expense_audit.expenses`'
bq query --use_legacy_sql=false \
  'TRUNCATE TABLE `YOUR_PROJECT.expense_audit.processing_status`'
```

## NON_DEDUCTIBLE_CATEGORY

All five categories are seeded as active, so no PDF can trigger this rule on its own.
Deactivate a limit and upload the matching invoice:

```sql
UPDATE `YOUR_PROJECT.expense_audit.category_limits`
SET active = FALSE
WHERE category = 'OTHER';
```

Then upload `12_valid_other.pdf`; the expected outcome is `NON_DEDUCTIBLE` with
`NON_DEDUCTIBLE_CATEGORY`. Re-enable the row with `SET active = TRUE` when finished.

## Uploading

Use the web page, or the API:

```bash
UPLOAD_URL="https://expense-audit-upload-vaqnk52hia-uc.a.run.app"
curl -sS -X POST "$UPLOAD_URL/upload" \
  -F "code=YOUR_ACCESS_CODE" \
  -F "file=@samples/scenarios/01_total_mismatch.pdf;type=application/pdf"
```

Poll `GET /status/{upload_id}` until the status is `COMPLETED` or `FAILED`.

The core `samples/README.md` covers `PER_EXPENSE_LIMIT_EXCEEDED`, `DUPLICATE_EXPENSE`,
`INVALID_RFC`, and the noisy-scan controlled case.
