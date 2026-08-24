"""Dataset selector for KITTI/YOLO directories and nuScenes relational graphs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DatasetType(StrEnum):
    KITTI = "kitti"
    NUSCENES = "nuscenes"


class DatasetScenario(StrEnum):
    BASELINE_EASY = "baseline_easy"
    CHALLENGING_HARD = "challenging_hard"


class DatasetLayoutError(ValueError):
    """Raised when the requested dataset layout is incomplete or invalid."""


@dataclass(frozen=True)
class ScenarioProfile:
    scenario: DatasetScenario
    dataset_type: DatasetType
    label: str
    description: str
    tags: tuple[str, ...]
    region: str
    lighting: str
    weather: str
    traffic_density: str
    risk_note: str


@dataclass(frozen=True)
class SelectedDataset:
    dataset_type: DatasetType
    dataset_root: Path
    version: str | None
    description: str
    scenario: DatasetScenario
    tags: tuple[str, ...]
    context: dict[str, str]


KITTI_REQUIRED_DIRECTORIES = ("image_2", "velodyne", "calib", "label_2")
YOLO_CLASS_FILENAMES = ("classes.txt", "class.txt", "class.txt.txt")
YOLO_CONFIG_EXTENSIONS = (".yaml", ".yml")
YOLO_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
NUSCENES_REQUIRED_TABLES = (
    "scene",
    "sample",
    "sample_data",
    "sample_annotation",
    "calibrated_sensor",
)
SCENARIO_PROFILES: dict[DatasetScenario, ScenarioProfile] = {
    DatasetScenario.BASELINE_EASY: ScenarioProfile(
        scenario=DatasetScenario.BASELINE_EASY,
        dataset_type=DatasetType.KITTI,
        label="Baseline / Easy scenarios",
        description="KITTI-style clean Karlsruhe daytime driving for baseline QA and smoke tests.",
        tags=("urban_daytime", "clear_weather", "mid_density", "europe"),
        region="Karlsruhe, Germany / Europe",
        lighting="daytime",
        weather="clear_weather",
        traffic_density="low_to_mid_density",
        risk_note="Clean data can hide model bias against rain, night, dense traffic, and multi-region behavior.",
    ),
    DatasetScenario.CHALLENGING_HARD: ScenarioProfile(
        scenario=DatasetScenario.CHALLENGING_HARD,
        dataset_type=DatasetType.NUSCENES,
        label="Challenging / Hard scenarios",
        description="nuScenes-style congested Boston/Singapore driving with night, rain, and dense actors.",
        tags=("congested_urban", "night_time", "rainy", "high_density", "multi_region"),
        region="Boston, USA and Singapore",
        lighting="day_and_night",
        weather="rainy_or_reflective_available",
        traffic_density="high_density",
        risk_note="Use this profile to stress models beyond the clean KITTI baseline.",
    ),
}
DATASET_DEFAULT_SCENARIO = {
    DatasetType.KITTI: DatasetScenario.BASELINE_EASY,
    DatasetType.NUSCENES: DatasetScenario.CHALLENGING_HARD,
}


def select_dataset(dataset_type: str, dataset_root: Path, *, nuscenes_version: str = "v1.0-mini") -> SelectedDataset:
    """Validate the requested dataset and return the normalized selector output."""
    return select_dataset_layout(dataset_type, dataset_root, nuscenes_version=nuscenes_version)


def scenario_profile(scenario: str | DatasetScenario) -> ScenarioProfile:
    """Return the canonical scenario profile for selector prompts and job metadata."""
    return SCENARIO_PROFILES[DatasetScenario(scenario)]


def scenario_for_dataset(dataset_type: str | DatasetType) -> DatasetScenario:
    """Return the default real-world scenario represented by a dataset family."""
    return DATASET_DEFAULT_SCENARIO[DatasetType(dataset_type)]


def select_dataset_layout(
    dataset_type: str,
    dataset_root: Path,
    *,
    nuscenes_version: str = "v1.0-mini",
    strict: bool = True,
    scenario: str | DatasetScenario | None = None,
) -> SelectedDataset:
    """Validate the requested dataset and return the normalized selector output."""
    parsed_type = DatasetType(dataset_type)
    parsed_scenario = DatasetScenario(scenario) if scenario else scenario_for_dataset(parsed_type)
    profile = scenario_profile(parsed_scenario)
    if profile.dataset_type != parsed_type:
        raise DatasetLayoutError(
            f"Scenario {parsed_scenario} maps to {profile.dataset_type}, but selector requested {parsed_type}."
        )
    root = Path(dataset_root)
    if parsed_type == DatasetType.KITTI:
        return _select_kitti(root, strict=strict, profile=profile)
    return _select_nuscenes(root, nuscenes_version, profile)


def _context(profile: ScenarioProfile) -> dict[str, str]:
    return {
        "label": profile.label,
        "region": profile.region,
        "lighting": profile.lighting,
        "weather": profile.weather,
        "traffic_density": profile.traffic_density,
        "risk_note": profile.risk_note,
    }


def _select_kitti(root: Path, *, strict: bool, profile: ScenarioProfile) -> SelectedDataset:
    layout_root = root / "training" if (root / "training").is_dir() else root
    if not strict and (root / "annotations.coco.json").is_file():
        return SelectedDataset(
            dataset_type=DatasetType.KITTI,
            dataset_root=root,
            version=None,
            description="KITTI converted mini fixture selected.",
            scenario=profile.scenario,
            tags=profile.tags,
            context=_context(profile),
        )
    if is_yolo_detection_layout(root):
        return SelectedDataset(
            dataset_type=DatasetType.KITTI,
            dataset_root=root,
            version=None,
            description="KITTI-derived YOLO detection directory selected.",
            scenario=profile.scenario,
            tags=profile.tags,
            context={**_context(profile), "annotation_format": "yolo"},
        )
    missing = [directory for directory in KITTI_REQUIRED_DIRECTORIES if not (layout_root / directory).is_dir()]
    if missing:
        expected = ", ".join(KITTI_REQUIRED_DIRECTORIES)
        rendered_missing = ", ".join(missing)
        raise DatasetLayoutError(
            f"KITTI flat directory is invalid at {root}. Missing: {rendered_missing}. "
            f"Expected directories under dataset root or training/: {expected}."
        )
    return SelectedDataset(
        dataset_type=DatasetType.KITTI,
        dataset_root=root,
        version=None,
        description="KITTI flat frame-by-frame directory selected.",
        scenario=profile.scenario,
        tags=profile.tags,
        context=_context(profile),
    )


def is_yolo_detection_layout(root: Path) -> bool:
    """Return whether ``root`` contains an ingestible YOLO detection dataset."""
    image_root = root / "images"
    label_root = root / "labels"
    if not image_root.is_dir() or not label_root.is_dir():
        return False
    has_class_metadata = any((root / filename).is_file() for filename in YOLO_CLASS_FILENAMES) or any(
        path.is_file() and path.suffix.lower() in YOLO_CONFIG_EXTENSIONS for path in root.iterdir()
    )
    if not has_class_metadata:
        return False

    direct_images = any(
        path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS for path in image_root.iterdir()
    )
    if direct_images:
        return True
    return any(
        split.is_dir()
        and (label_root / split.name).is_dir()
        and any(path.is_file() and path.suffix.lower() in YOLO_IMAGE_EXTENSIONS for path in split.iterdir())
        for split in image_root.iterdir()
    )


def _select_nuscenes(root: Path, version: str, profile: ScenarioProfile) -> SelectedDataset:
    metadata_root = root / version
    missing = [f"{name}.json" for name in NUSCENES_REQUIRED_TABLES if not (metadata_root / f"{name}.json").is_file()]
    if missing:
        rendered_missing = ", ".join(missing)
        expected = ", ".join(f"{name}.json" for name in NUSCENES_REQUIRED_TABLES)
        raise DatasetLayoutError(
            f"nuScenes relational graph is invalid at {root}. Missing under {metadata_root}: {rendered_missing}. "
            f"Expected JSON tables: {expected}."
        )
    return SelectedDataset(
        dataset_type=DatasetType.NUSCENES,
        dataset_root=root,
        version=version,
        description="nuScenes relational token graph selected.",
        scenario=profile.scenario,
        tags=profile.tags,
        context=_context(profile),
    )
