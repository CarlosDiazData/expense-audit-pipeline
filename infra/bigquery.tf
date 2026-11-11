resource "google_bigquery_dataset" "expense_audit" {
  dataset_id = local.dataset_id
  location   = var.region

  depends_on = [google_project_service.enabled]
}

resource "google_bigquery_table" "expenses" {
  dataset_id = google_bigquery_dataset.expense_audit.dataset_id
  table_id   = "expenses"

  schema = jsonencode([
    { name = "expense_id", type = "STRING", mode = "NULLABLE" },
    { name = "upload_id", type = "STRING", mode = "NULLABLE" },
    { name = "source_object", type = "STRING", mode = "NULLABLE" },
    { name = "original_filename", type = "STRING", mode = "NULLABLE" },
    { name = "rfc_emisor", type = "STRING", mode = "NULLABLE" },
    { name = "rfc_receptor", type = "STRING", mode = "NULLABLE" },
    { name = "expense_date", type = "DATE", mode = "NULLABLE" },
    { name = "subtotal", type = "NUMERIC", mode = "NULLABLE" },
    { name = "iva", type = "NUMERIC", mode = "NULLABLE" },
    { name = "total", type = "NUMERIC", mode = "NULLABLE" },
    { name = "currency", type = "STRING", mode = "NULLABLE" },
    { name = "category", type = "STRING", mode = "NULLABLE" },
    { name = "vendor_name", type = "STRING", mode = "NULLABLE" },
    { name = "description", type = "STRING", mode = "NULLABLE" },
    { name = "policy_status", type = "STRING", mode = "NULLABLE" },
    { name = "policy_reasons", type = "STRING", mode = "REPEATED" },
    { name = "policy_details", type = "JSON", mode = "NULLABLE" },
    { name = "llm_model", type = "STRING", mode = "NULLABLE" },
    { name = "llm_raw_response", type = "JSON", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "processed_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["policy_status", "category"]
}

resource "google_bigquery_table" "processing_status" {
  dataset_id = google_bigquery_dataset.expense_audit.dataset_id
  table_id   = "processing_status"

  schema = jsonencode([
    { name = "upload_id", type = "STRING", mode = "REQUIRED" },
    { name = "original_filename", type = "STRING", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "NULLABLE" },
    { name = "attempts", type = "INT64", mode = "NULLABLE" },
    { name = "error_code", type = "STRING", mode = "NULLABLE" },
    { name = "error_message", type = "STRING", mode = "NULLABLE" },
    { name = "created_at", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "updated_at", type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["status"]
}

resource "google_bigquery_table" "category_limits" {
  dataset_id = google_bigquery_dataset.expense_audit.dataset_id
  table_id   = "category_limits"

  schema = jsonencode([
    { name = "category", type = "STRING", mode = "REQUIRED" },
    { name = "per_expense_limit", type = "NUMERIC", mode = "REQUIRED" },
    { name = "monthly_limit", type = "NUMERIC", mode = "REQUIRED" },
    { name = "currency", type = "STRING", mode = "REQUIRED" },
    { name = "active", type = "BOOL", mode = "REQUIRED" },
  ])
}

resource "google_bigquery_job" "seed_category_limits" {
  job_id   = "seed-expense-audit-category-limits"
  location = var.region

  query {
    query          = <<-SQL
      MERGE `${var.project_id}.${local.dataset_id}.category_limits` AS target
      USING (
        SELECT * FROM UNNEST([
          STRUCT('FOOD' AS category, NUMERIC '50.00' AS per_expense_limit, NUMERIC '500.00' AS monthly_limit, 'MXN' AS currency, TRUE AS active),
          STRUCT('TRANSPORT', NUMERIC '200.00', NUMERIC '2000.00', 'MXN', TRUE),
          STRUCT('SOFTWARE', NUMERIC '500.00', NUMERIC '3000.00', 'MXN', TRUE),
          STRUCT('LODGING', NUMERIC '300.00', NUMERIC '3000.00', 'MXN', TRUE),
          STRUCT('OTHER', NUMERIC '100.00', NUMERIC '1000.00', 'MXN', TRUE)
        ])
      ) AS source
      ON target.category = source.category
      WHEN MATCHED THEN UPDATE SET
        per_expense_limit = source.per_expense_limit,
        monthly_limit = source.monthly_limit,
        currency = source.currency,
        active = source.active
      WHEN NOT MATCHED THEN INSERT
        (category, per_expense_limit, monthly_limit, currency, active)
      VALUES
        (source.category, source.per_expense_limit, source.monthly_limit, source.currency, source.active)
    SQL
    use_legacy_sql = false
  }

  depends_on = [google_bigquery_table.category_limits]
}
