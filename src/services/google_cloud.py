"""Shared Google Cloud client construction for API and ingestion runtimes."""

from __future__ import annotations

import json
from typing import Any

from src.config import IngestionSettings


def create_gcs_storage_client(settings: IngestionSettings) -> Any:
    try:
        from google.cloud import storage  # type: ignore[import-untyped]
        from google.oauth2 import service_account  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("Google Cloud Storage support requires `pip install -e '.[cloud]'`.") from error

    if settings.gcs_credentials_json:
        try:
            credential_info = json.loads(settings.gcs_credentials_json.get_secret_value())
        except json.JSONDecodeError as error:
            raise ValueError("LABEL_GUARDIAN_GCS_CREDENTIALS_JSON must be valid JSON.") from error
        if not isinstance(credential_info, dict):
            raise ValueError("LABEL_GUARDIAN_GCS_CREDENTIALS_JSON must contain a JSON object.")
        credentials = service_account.Credentials.from_service_account_info(credential_info)
        project = settings.gcs_project or credential_info.get("project_id")
        return storage.Client(project=project, credentials=credentials)

    if settings.gcs_credentials_path:
        return storage.Client.from_service_account_json(
            str(settings.gcs_credentials_path),
            project=settings.gcs_project,
        )

    return storage.Client(project=settings.gcs_project)
