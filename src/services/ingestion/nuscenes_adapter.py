"""nuScenes-style 3D cuboid projection into Label Guardian QA objects."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

from src.models.ingestion import (
    AnnotationProvenance,
    AnnotationSource,
    BoundingBox,
    QAObjectPayload,
    QAReviewStatus,
)
from src.services.ingestion.kitti_adapter import ImageMetadata

NUSCENES_CAMERA_CHANNEL_ORDER = (
    "CAM_FRONT",
    "CAM_FRONT_RIGHT",
    "CAM_BACK_RIGHT",
    "CAM_BACK",
    "CAM_BACK_LEFT",
    "CAM_FRONT_LEFT",
)


class NuScenesDatasetLayoutError(ValueError):
    """Raised when a nuScenes dataset has not been downloaded or unpacked."""


def _quaternion_to_rotation(quaternion: ArrayLike) -> NDArray[np.float64]:
    """Convert a nuScenes scalar-first quaternion into a 3x3 rotation matrix."""
    w, x, y, z = np.asarray(quaternion, dtype=float)
    scale = np.linalg.norm([w, x, y, z])
    if scale == 0:
        raise ValueError("quaternion must not be zero")
    w, x, y, z = np.array([w, x, y, z]) / scale
    return cast(
        NDArray[np.float64],
        np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ],
            dtype=np.float64,
        ),
    )


def _quaternion_yaw(quaternion: ArrayLike) -> float:
    """Return the global z-axis yaw in radians from a scalar-first quaternion."""
    w, x, y, z = np.asarray(quaternion, dtype=float)
    normalized = np.array([w, x, y, z]) / np.linalg.norm([w, x, y, z])
    w, x, y, z = normalized
    return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _inverse_transform(translation: ArrayLike, rotation: ArrayLike) -> NDArray[np.float64]:
    matrix = np.eye(4)
    rotation_matrix = _quaternion_to_rotation(rotation)
    matrix[:3, :3] = rotation_matrix.T
    matrix[:3, 3] = -rotation_matrix.T @ np.asarray(translation, dtype=float)
    return matrix


def cuboid_corners(translation: ArrayLike, size: ArrayLike, rotation: ArrayLike) -> NDArray[np.float64]:
    """Build eight global cuboid corners from a nuScenes annotation pose.

    nuScenes sizes are width, length, height; x represents length and y width.
    """
    width, length, height = np.asarray(size, dtype=float)
    local = np.array(
        [
            [length / 2, width / 2, height / 2],
            [length / 2, -width / 2, height / 2],
            [-length / 2, -width / 2, height / 2],
            [-length / 2, width / 2, height / 2],
            [length / 2, width / 2, -height / 2],
            [length / 2, -width / 2, -height / 2],
            [-length / 2, -width / 2, -height / 2],
            [-length / 2, width / 2, -height / 2],
        ]
    )
    result = (_quaternion_to_rotation(rotation) @ local.T).T + np.asarray(translation, dtype=float)
    return cast(NDArray[np.float64], result)


@dataclass(frozen=True)
class NuScenesAdapter:
    """Load standard nuScenes metadata tables without requiring the devkit."""

    dataset_root: Path
    version: str = "v1.0-mini"
    max_images: int | None = None

    def load(self) -> tuple[list[ImageMetadata], list[QAObjectPayload]]:
        metadata_root = self.dataset_root / self.version
        required_tables = (
            "sample",
            "sample_data",
            "sample_annotation",
            "calibrated_sensor",
            "ego_pose",
            "category",
        )
        missing = [
            metadata_root / f"{name}.json" for name in required_tables if not (metadata_root / f"{name}.json").is_file()
        ]
        if missing:
            rendered_missing = ", ".join(str(path) for path in missing)
            raise NuScenesDatasetLayoutError(
                f"nuScenes dataset is not available at {self.dataset_root}. Missing: {rendered_missing}. "
                "Download and unpack the requested split so it contains samples/ and "
                f"{self.version}/, then pass that parent folder with --dataset-root."
            )
        tables = {
            name: json.loads((metadata_root / f"{name}.json").read_text(encoding="utf-8")) for name in required_tables
        }
        optional_tables = {
            name: json.loads((metadata_root / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("scene", "sensor")
            if (metadata_root / f"{name}.json").is_file()
        }
        instance_path = metadata_root / "instance.json"
        instances = json.loads(instance_path.read_text(encoding="utf-8")) if instance_path.is_file() else []
        calibrated = {row["token"]: row for row in tables["calibrated_sensor"]}
        ego_poses = {row["token"]: row for row in tables["ego_pose"]}
        categories = {row["token"]: row["name"] for row in tables["category"]}
        samples = {row["token"]: row for row in tables["sample"]}
        scenes = {row["token"]: row for row in optional_tables.get("scene", [])}
        sensors = {row["token"]: row for row in optional_tables.get("sensor", [])}
        instance_categories = {
            row["token"]: categories[row["category_token"]]
            for row in instances
            if row.get("category_token") in categories
        }
        images: list[ImageMetadata] = []
        camera_data_by_sample: dict[str, list[dict]] = {}
        for row in tables["sample_data"]:
            sensor = calibrated[row["calibrated_sensor_token"]]
            sensor_metadata = sensors.get(sensor.get("sensor_token", ""), {})
            filename_parts = Path(row.get("filename", "")).parts
            is_keyframe = row.get("is_key_frame", True)
            is_sample_image = len(filename_parts) >= 2 and filename_parts[0] == "samples"
            is_camera = sensor_metadata.get("modality") in (None, "camera") and bool(sensor.get("camera_intrinsic"))
            if sensor["sensor_token"] and is_camera and is_keyframe and is_sample_image:
                camera_data_by_sample.setdefault(row["sample_token"], []).append(row)
        channel_order = {channel: index for index, channel in enumerate(NUSCENES_CAMERA_CHANNEL_ORDER)}
        for cameras in camera_data_by_sample.values():
            cameras.sort(
                key=lambda camera: channel_order.get(
                    sensors.get(calibrated[camera["calibrated_sensor_token"]].get("sensor_token", ""), {}).get(
                        "channel",
                        Path(camera["filename"]).parts[-2] if len(Path(camera["filename"]).parts) >= 2 else "",
                    ),
                    len(channel_order),
                )
            )
        selected_sample_tokens = sorted(
            camera_data_by_sample,
            key=lambda sample_token: (
                samples.get(sample_token, {}).get("timestamp", 0),
                sample_token,
            ),
        )
        if self.max_images is not None:
            selected_sample_tokens = selected_sample_tokens[: self.max_images]
        selected_camera_tokens: set[str] = set()
        for sample_token in selected_sample_tokens:
            sample = samples.get(sample_token, {})
            scene_token = sample.get("scene_token")
            scene_name = scenes.get(scene_token, {}).get("name") if scene_token else None
            frame_group = str(scene_name or sample_token)
            for camera in camera_data_by_sample[sample_token]:
                path = self.dataset_root / camera["filename"]
                from PIL import Image

                with Image.open(path) as image:
                    width, height = image.size
                sensor = calibrated[camera["calibrated_sensor_token"]]
                channel = sensors.get(sensor.get("sensor_token", ""), {}).get("channel")
                if channel is None:
                    parts = Path(camera["filename"]).parts
                    channel = parts[-2] if len(parts) >= 2 else "camera"
                suffix = Path(camera["filename"]).suffix or ".jpg"
                storage_filename = f"{frame_group}/{sample_token}/{channel}{suffix}"
                images.append(
                    ImageMetadata(
                        camera["token"],
                        camera["filename"],
                        width,
                        height,
                        storage_filename=storage_filename,
                    )
                )
                selected_camera_tokens.add(camera["token"])
        cases: list[QAObjectPayload] = []
        for annotation in tables["sample_annotation"]:
            global_corners = cuboid_corners(annotation["translation"], annotation["size"], annotation["rotation"])
            for camera in camera_data_by_sample.get(annotation["sample_token"], []):
                if camera["token"] not in selected_camera_tokens:
                    continue
                camera_calibration = calibrated[camera["calibrated_sensor_token"]]
                camera_pose = ego_poses[camera["ego_pose_token"]]
                sensor = sensors.get(camera_calibration.get("sensor_token", "")) or {}
                parts = Path(camera["filename"]).parts
                camera_channel = sensor.get("channel") or (parts[-2] if len(parts) >= 2 else None)
                extrinsic = _inverse_transform(
                    camera_calibration["translation"], camera_calibration["rotation"]
                ) @ _inverse_transform(camera_pose["translation"], camera_pose["rotation"])
                label = (
                    annotation.get("category_name")
                    or categories.get(annotation.get("category_token", ""))
                    or instance_categories.get(annotation.get("instance_token", ""))
                )
                if label is None:
                    raise NuScenesDatasetLayoutError(
                        f"nuScenes annotation {annotation.get('token')} does not include category_name, "
                        "a known category_token, or an instance_token with a known category."
                    )
                qa_object = project_cuboid_to_qa_object(
                    source_image_id=camera["token"],
                    label=label,
                    corners=global_corners,
                    extrinsic=extrinsic,
                    intrinsic=np.asarray(camera_calibration["camera_intrinsic"]),
                    source_annotation_id=annotation["token"],
                    source_metadata={
                        "translation_xyz": annotation["translation"],
                        "size_wlh": annotation["size"],
                        "yaw_radians": _quaternion_yaw(annotation["rotation"]),
                        "timestamp": camera.get("timestamp"),
                        "camera_channel": camera_channel,
                    },
                )
                if qa_object is not None:
                    cases.append(qa_object)
        return images, cases


def _as_matrix(values: ArrayLike, shape: tuple[int, int], name: str) -> NDArray[np.float64]:
    matrix = np.asarray(values, dtype=float)
    if matrix.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {matrix.shape}")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} must contain only finite values")
    return cast(NDArray[np.float64], matrix)


def project_cuboid_to_bbox(
    corners: ArrayLike,
    extrinsic: ArrayLike,
    intrinsic: ArrayLike,
) -> BoundingBox | None:
    """Project eight 3D corners using LiDAR/global-to-camera calibration.

    Corners at camera depth zero or below are excluded before their pixels are
    calculated. ``None`` means the cuboid has no camera-visible corner.
    """
    corner_array = _as_matrix(corners, (8, 3), "corners")
    extrinsic_matrix = _as_matrix(extrinsic, (4, 4), "extrinsic")
    intrinsic_matrix = _as_matrix(intrinsic, (3, 3), "intrinsic")

    homogeneous_corners = np.concatenate((corner_array, np.ones((8, 1))), axis=1)
    camera_points = (extrinsic_matrix @ homogeneous_corners.T).T
    visible_camera_points = camera_points[camera_points[:, 2] > 0]
    if not len(visible_camera_points):
        return None

    image_points = (intrinsic_matrix @ visible_camera_points[:, :3].T).T
    valid_projection = np.abs(image_points[:, 2]) > np.finfo(float).eps
    image_points = image_points[valid_projection]
    if not len(image_points):
        return None
    pixels = image_points[:, :2] / image_points[:, 2:3]
    try:
        return BoundingBox(
            xmin=float(np.min(pixels[:, 0])),
            ymin=float(np.min(pixels[:, 1])),
            xmax=float(np.max(pixels[:, 0])),
            ymax=float(np.max(pixels[:, 1])),
        )
    except ValueError:
        return None


def project_cuboid_to_qa_object(
    *,
    source_image_id: str,
    label: str,
    corners: ArrayLike,
    extrinsic: ArrayLike,
    intrinsic: ArrayLike,
    source_annotation_id: str,
    source_metadata: dict[str, object] | None = None,
) -> QAObjectPayload | None:
    """Return a QA-object payload for a visible nuScenes cuboid."""
    bbox = project_cuboid_to_bbox(corners, extrinsic, intrinsic)
    if bbox is None:
        return None
    corners_matrix = _as_matrix(corners, (8, 3), "corners")
    extrinsic_matrix = _as_matrix(extrinsic, (4, 4), "extrinsic")
    intrinsic_matrix = _as_matrix(intrinsic, (3, 3), "intrinsic")
    return QAObjectPayload(
        source_image_id=source_image_id,
        label=label,
        bbox=bbox,
        review_status=QAReviewStatus.VERIFIED,
        provenance=[
            AnnotationProvenance(
                source=AnnotationSource.NUSCENES,
                source_annotation_id=source_annotation_id,
                bbox=bbox,
                raw={"coordinate_frame": "lidar_or_global", **(source_metadata or {})},
            )
        ],
        calibration={"intrinsic": intrinsic_matrix.tolist(), "extrinsic": extrinsic_matrix.tolist()},
        cuboid_corners=corners_matrix.tolist(),
    )
