resource "google_storage_bucket" "landing" {
  name                        = local.landing_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket" "function_source" {
  name                        = local.source_bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  depends_on = [google_project_service.enabled]
}

data "archive_file" "processor" {
  type        = "zip"
  source_dir  = var.processor_source_dir
  output_path = "${path.module}/.terraform/processor.zip"
}

resource "google_storage_bucket_object" "processor" {
  name   = "processor-${data.archive_file.processor.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.processor.output_path
}
