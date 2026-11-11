resource "google_artifact_registry_repository" "upload" {
  location      = var.region
  repository_id = "expense-audit"
  description   = "Cloud Run upload service image"
  format        = "DOCKER"

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret" "access_code" {
  secret_id = "expense-audit-access-code"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "access_code" {
  secret      = google_secret_manager_secret.access_code.id
  secret_data = var.access_code
}
