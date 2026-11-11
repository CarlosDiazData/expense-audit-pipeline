output "upload_url" {
  description = "Public Cloud Run URL for the demo page."
  value       = google_cloud_run_v2_service.upload.uri
}

output "landing_bucket" {
  description = "GCS landing bucket name."
  value       = google_storage_bucket.landing.name
}

output "dataset" {
  description = "BigQuery dataset ID."
  value       = google_bigquery_dataset.expense_audit.dataset_id
}

output "processor_function" {
  description = "Cloud Function Gen2 name."
  value       = google_cloudfunctions2_function.processor.name
}
