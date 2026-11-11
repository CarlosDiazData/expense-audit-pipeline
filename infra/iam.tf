resource "google_service_account" "uploader" {
  account_id   = "sa-uploader"
  display_name = "Expense audit uploader"
}

resource "google_service_account" "processor" {
  account_id   = "sa-processor"
  display_name = "Expense audit processor"
}

resource "google_storage_bucket_iam_member" "uploader_object_creator" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.uploader.email}"
}

resource "google_storage_bucket_iam_member" "processor_object_viewer" {
  bucket = google_storage_bucket.landing.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_bigquery_dataset_iam_member" "uploader_data_editor" {
  dataset_id = google_bigquery_dataset.expense_audit.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.uploader.email}"
}

resource "google_bigquery_dataset_iam_member" "processor_data_editor" {
  dataset_id = google_bigquery_dataset.expense_audit.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_secret_manager_secret_iam_member" "uploader_secret_accessor" {
  secret_id = google_secret_manager_secret.access_code.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.uploader.email}"
}

resource "google_project_iam_member" "processor_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_project_iam_member" "processor_eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

data "google_project" "current" {
  project_id = var.project_id
}

# Eventarc creates a Pub/Sub topic for Cloud Storage triggers; the GCS service
# agent must be able to publish to it.
resource "google_project_iam_member" "gcs_service_agent_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gs-project-accounts.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "uploader_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.uploader.email}"
}

resource "google_project_iam_member" "processor_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.processor.email}"
}
