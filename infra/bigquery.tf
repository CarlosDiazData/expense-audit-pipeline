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
  job_id   = "seed-expense-audit-category-limits-v2"
  location = var.region

  query {
    query             = <<-SQL
      SELECT 'FOOD' AS category, NUMERIC '50.00' AS per_expense_limit, NUMERIC '500.00' AS monthly_limit, 'MXN' AS currency, TRUE AS active
      UNION ALL SELECT 'TRANSPORT', NUMERIC '200.00', NUMERIC '2000.00', 'MXN', TRUE
      UNION ALL SELECT 'SOFTWARE', NUMERIC '500.00', NUMERIC '3000.00', 'MXN', TRUE
      UNION ALL SELECT 'LODGING', NUMERIC '300.00', NUMERIC '3000.00', 'MXN', TRUE
      UNION ALL SELECT 'OTHER', NUMERIC '100.00', NUMERIC '1000.00', 'MXN', TRUE
    SQL
    use_legacy_sql    = false
    write_disposition = "WRITE_TRUNCATE"

    destination_table {
      project_id = var.project_id
      dataset_id = local.dataset_id
      table_id   = "category_limits"
    }
  }

  depends_on = [google_bigquery_table.category_limits]
}
