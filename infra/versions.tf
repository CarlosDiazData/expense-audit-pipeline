terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Optional remote state. Uncomment and adjust to use a GCS backend.
  # backend "gcs" {
  #   bucket = "my-terraform-state-bucket"
  #   prefix = "expense-audit"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
