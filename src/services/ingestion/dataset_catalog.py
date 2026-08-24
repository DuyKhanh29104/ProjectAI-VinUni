"""Official autonomous-driving dataset package catalog and selection rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.services.ingestion.dataset_selector import DatasetType


class PackageReadiness(StrEnum):
    READY = "ready"
    PLANNED = "planned"


@dataclass(frozen=True)
class DatasetPackage:
    package_id: str
    dataset_type: DatasetType
    version: str | None
    topics: frozenset[str]
    description: str
    storage_segment: str
    readiness: PackageReadiness
    official_page: str


DATASET_CATALOG: tuple[DatasetPackage, ...] = (
    DatasetPackage(
        "kitti-object-detection",
        DatasetType.KITTI,
        None,
        frozenset({"2d"}),
        "KITTI Object Detection 2D: PNG camera images plus label_2 text annotations.",
        "object-detection",
        PackageReadiness.READY,
        "https://www.cvlibs.net/datasets/kitti/eval_object.php",
    ),
    DatasetPackage(
        "nuscenes-v1.0-mini",
        DatasetType.NUSCENES,
        "v1.0-mini",
        frozenset({"2d", "3d"}),
        "nuScenes mini: camera/LiDAR, relational JSON, cuboids and 2D projection.",
        "v1.0-mini",
        PackageReadiness.READY,
        "https://www.nuscenes.org/nuscenes",
    ),
)


def catalog_package(package_id: str) -> DatasetPackage:
    """Return a supported catalog package by its stable selector id."""
    for package in DATASET_CATALOG:
        if package.package_id == package_id:
            return package
    raise ValueError(f"Unknown dataset package: {package_id}")


def select_catalog_packages(
    *, dataset_count: int, topic: str, dataset_type: DatasetType | None = None
) -> list[DatasetPackage]:
    """Select a deterministic set of ready packages for a package-level ingest request."""
    if dataset_count < 1:
        raise ValueError("dataset_count must be at least 1")
    candidates = [
        package
        for package in DATASET_CATALOG
        if package.readiness == PackageReadiness.READY
        and topic in package.topics
        and (dataset_type is None or package.dataset_type == dataset_type)
    ]
    if dataset_count > len(candidates):
        available = ", ".join(package.package_id for package in candidates) or "none"
        raise ValueError(
            f"Requested {dataset_count} complete packages but only {len(candidates)} are ingest-ready: {available}"
        )
    return candidates[:dataset_count]
