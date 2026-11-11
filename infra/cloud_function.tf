resource "google_cloudfunctions2_function" "processor" {
  name     = "expense-audit-processor"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = "process_ticket"

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.processor.name
      }
    }
  }

  service_config {
    max_instance_count    = 5
    min_instance_count    = 0
    available_memory      = "512M"
    timeout_seconds       = 120
    service_account_email = google_service_account.processor.email

    environment_variables = {
      GCP_PROJECT        = var.project_id
      BQ_DATASET         = google_bigquery_dataset.expense_audit.dataset_id
      GEMINI_MODEL       = var.gemini_model
      GEMINI_LOCATION    = var.region
      COMPANY_RFC        = var.company_rfc
      GCS_ALLOWED_BUCKET = google_storage_bucket.landing.name
      MAX_UPLOAD_MB      = tostring(var.max_upload_mb)
      MAX_ATTEMPTS       = "5"
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.storage.object.v1.finalized"
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = google_service_account.processor.email

    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.landing.name
    }

    event_filters {
      attribute = "name"
      operator  = "match-path-pattern"
      value     = "uploads/**"
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_storage_bucket_object.processor,
    google_project_iam_member.processor_eventarc_receiver,
  ]
}
