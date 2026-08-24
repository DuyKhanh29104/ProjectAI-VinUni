"""Opt-in test against the configured Google Cloud Storage bucket.

Set LABEL_GUARDIAN_GCS_INTEGRATION=1 and the LABEL_GUARDIAN_GCS_* settings before
running this test. It uses the dedicated PostgreSQL test database and the configured
bucket.
"""

import os
from pathlib import Path

import pytest

from src.config import IngestionSettings
from src.services.ingestion.ingestion_service import (
    IngestionService,
    create_object_storage_client,
)

pytestmark = pytest.mark.skipif(
    os.getenv("LABEL_GUARDIAN_GCS_INTEGRATION") != "1",
    reason="set LABEL_GUARDIAN_GCS_INTEGRATION=1 to run against GCS",
)


def test_ingests_fixture_into_configured_gcs(postgres_sync_session_factory):
    settings = IngestionSettings()
    result = IngestionService(
        Path("eval/label_guardian_ingestion_mini"),
        postgres_sync_session_factory,
        create_object_storage_client(settings),
        settings,
    ).ingest()
    assert result.images == 12
