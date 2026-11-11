from __future__ import annotations

import functions_framework
from google import genai
from google.cloud import bigquery, storage

from expense_audit.adapters.bigquery import BigQueryRepository
from expense_audit.adapters.gcs import GcsStorage
from expense_audit.adapters.gemini import GeminiExtractor
from expense_audit.config import Settings
from expense_audit.processor import ProcessorDeps, run_processing


def build_deps(settings: Settings | None = None) -> ProcessorDeps:
    settings = settings or Settings.from_env()
    bucket_name = settings.gcs_allowed_bucket or settings.landing_bucket
    return ProcessorDeps(
        repo=BigQueryRepository(
            bigquery.Client(project=settings.gcp_project),
            project=settings.gcp_project,
            dataset=settings.bq_dataset,
        ),
        storage=GcsStorage(storage.Client(project=settings.gcp_project), bucket_name=bucket_name),
        extractor=GeminiExtractor(
            genai.Client(
                vertexai=True,
                project=settings.gcp_project,
                location=settings.gemini_location,
            ),
            settings.gemini_model,
        ),
        settings=settings,
    )


@functions_framework.cloud_event
def process_ticket(cloud_event) -> str:
    return run_processing(dict(cloud_event.data), build_deps())
