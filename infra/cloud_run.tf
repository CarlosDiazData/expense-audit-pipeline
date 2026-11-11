resource "google_cloud_run_v2_service" "upload" {
  name     = "expense-audit-upload"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.uploader.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = local.upload_image

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "LANDING_BUCKET"
        value = google_storage_bucket.landing.name
      }
      env {
        name  = "BQ_DATASET"
        value = google_bigquery_dataset.expense_audit.dataset_id
      }
      env {
        name  = "ACCESS_CODE_SECRET"
        value = google_secret_manager_secret.access_code.secret_id
      }
      env {
        name  = "MAX_UPLOAD_MB"
        value = tostring(var.max_upload_mb)
      }
      env {
        name  = "RATE_LIMIT_PER_HOUR"
        value = tostring(var.rate_limit_per_hour)
      }
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_secret_manager_secret_version.access_code,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.upload.location
  name     = google_cloud_run_v2_service.upload.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
