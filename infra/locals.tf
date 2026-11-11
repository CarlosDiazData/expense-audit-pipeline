locals {
  dataset_id     = "expense_audit"
  landing_bucket = "${var.project_id}-expense-audit-landing"
  source_bucket  = "${var.project_id}-expense-audit-source"
  upload_image = (
    var.upload_image != ""
    ? var.upload_image
    : "${var.region}-docker.pkg.dev/${var.project_id}/expense-audit/upload:latest"
  )
  uploader_sa  = "sa-uploader@${var.project_id}.iam.gserviceaccount.com"
  processor_sa = "sa-processor@${var.project_id}.iam.gserviceaccount.com"
}
