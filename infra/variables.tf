variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Region for all resources."
  type        = string
  default     = "us-central1"
}

variable "company_rfc" {
  description = "Company RFC used by the RECEPTOR_NOT_COMPANY rule. Empty disables the rule."
  type        = string
  default     = ""
}

variable "gemini_model" {
  description = "Vertex AI Gemini model used for extraction."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "access_code" {
  description = "Shared demo access code stored in Secret Manager."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.access_code) >= 12
    error_message = "The access code must be at least 12 characters long."
  }
}

variable "max_upload_mb" {
  description = "Maximum upload size in megabytes."
  type        = number
  default     = 10
}

variable "rate_limit_per_hour" {
  description = "Best-effort uploads allowed per client IP per hour, per instance."
  type        = number
  default     = 10
}

variable "upload_image" {
  description = "Cloud Run upload image. Empty uses the Artifact Registry convention."
  type        = string
  default     = ""
}

variable "processor_source_dir" {
  description = "Directory assembled by `make build` with the Cloud Function source."
  type        = string
  default     = "../build/processor"
}
