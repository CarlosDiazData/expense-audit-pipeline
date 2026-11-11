# Synthetic samples

Six synthetic invoices generated with `make samples` (`scripts/generate_samples.py`).
They are intentionally small PDFs for the demo; they are not real fiscal documents.

| File | Expected outcome |
|---|---|
| `01_valid_food.pdf` | `COMPLETED` / `VALID` (46.40 MXN, FOOD, under the 50 MXN per-expense limit) |
| `02_over_limit_transport.pdf` | `COMPLETED` / `SUSPICIOUS` with `PER_EXPENSE_LIMIT_EXCEEDED` (350 MXN transport) |
| `03_duplicate_a.pdf` | `COMPLETED` / `VALID` (first of the duplicate pair) |
| `04_duplicate_b.pdf` | `COMPLETED` / `SUSPICIOUS` with `DUPLICATE_EXPENSE` |
| `05_invalid_rfc.pdf` | `COMPLETED` / `NON_DEDUCTIBLE` with `INVALID_RFC` |
| `06_noisy_scan.pdf` | Controlled noisy variant: `COMPLETED` with an extracted result, or `FAILED` with `EXTRACTION_FAILED` |

The e2e script treats `06_noisy_scan.pdf` as a controlled outcome and reports whatever
the extraction produced.

## Scenario pack

The `scenarios/` directory contains additional invoices for `TOTAL_MISMATCH`,
`DATE_IN_FUTURE`, `INVALID_AMOUNT`, `CURRENCY_UNSUPPORTED`, `RECEPTOR_NOT_COMPANY`,
`MISSING_CRITICAL_FIELDS`, tolerance boundaries, each valid category, and a monthly
budget sequence. See [`scenarios/README.md`](scenarios/README.md) for expected
outcomes and upload order.
