import pytest

from src.services.ingestion.dataset_catalog import PackageReadiness, select_catalog_packages
from src.services.ingestion.dataset_selector import DatasetType


def test_selects_ready_packages_by_count_and_topic():
    packages = select_catalog_packages(dataset_count=2, topic="2d")

    assert [package.package_id for package in packages] == ["kitti-object-detection", "nuscenes-v1.0-mini"]
    assert all(package.readiness == PackageReadiness.READY for package in packages)


def test_selects_kitti_complete_package_only():
    packages = select_catalog_packages(dataset_count=1, topic="2d", dataset_type=DatasetType.KITTI)

    assert [package.package_id for package in packages] == ["kitti-object-detection"]


def test_rejects_package_count_above_ingest_ready_catalog():
    with pytest.raises(ValueError, match="only 1 are ingest-ready"):
        select_catalog_packages(dataset_count=2, topic="3d")


def test_rejects_zero_package_request():
    with pytest.raises(ValueError, match="at least 1"):
        select_catalog_packages(dataset_count=0, topic="2d")
