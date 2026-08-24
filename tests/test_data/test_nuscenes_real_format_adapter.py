import json
from pathlib import Path

import pytest
from PIL import Image

from src.services.ingestion.nuscenes_adapter import NuScenesAdapter, NuScenesDatasetLayoutError


def _write_table(root: Path, name: str, payload: list[dict]) -> None:
    (root / "v1.0-mini").mkdir(parents=True, exist_ok=True)
    (root / "v1.0-mini" / f"{name}.json").write_text(json.dumps(payload))


def test_reads_standard_nuscenes_metadata_and_projects_annotation(tmp_path: Path):
    image_path = tmp_path / "samples/CAM_FRONT/frame.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 80)).save(image_path)
    identity = [1, 0, 0, 0]
    _write_table(tmp_path, "sample", [{"token": "sample-1"}])
    _write_table(
        tmp_path,
        "sample_data",
        [
            {
                "token": "camera-1",
                "sample_token": "sample-1",
                "calibrated_sensor_token": "camera-calibration",
                "ego_pose_token": "ego-1",
                "filename": "samples/CAM_FRONT/frame.png",
            }
        ],
    )
    _write_table(
        tmp_path,
        "calibrated_sensor",
        [
            {
                "token": "camera-calibration",
                "sensor_token": "sensor-1",
                "translation": [0, 0, 0],
                "rotation": identity,
                "camera_intrinsic": [[100, 0, 50], [0, 100, 40], [0, 0, 1]],
            }
        ],
    )
    _write_table(tmp_path, "ego_pose", [{"token": "ego-1", "translation": [0, 0, 0], "rotation": identity}])
    _write_table(tmp_path, "category", [{"token": "car-category", "name": "vehicle.car"}])
    _write_table(
        tmp_path,
        "sample_annotation",
        [
            {
                "token": "annotation-1",
                "sample_token": "sample-1",
                "category_name": "vehicle.car",
                "translation": [0, 0, 10],
                "size": [2, 2, 2],
                "rotation": identity,
            }
        ],
    )
    images, cases = NuScenesAdapter(tmp_path).load()
    assert len(images) == 1
    assert images[0].filename == "samples/CAM_FRONT/frame.png"
    assert len(cases) == 1
    assert cases[0].label == "vehicle.car"
    assert cases[0].bbox.as_xyxy() == pytest.approx([38.8889, 28.8889, 61.1111, 51.1111])


def test_reports_an_actionable_error_when_dataset_is_not_downloaded(tmp_path: Path):
    with pytest.raises(NuScenesDatasetLayoutError, match="Download and unpack"):
        NuScenesAdapter(tmp_path).load()


def test_max_images_limits_nuscenes_frames_not_camera_views(tmp_path: Path):
    for channel in ("CAM_FRONT", "CAM_BACK"):
        image_path = tmp_path / f"samples/{channel}/sample-1.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 80)).save(image_path)
    for channel in ("CAM_FRONT", "CAM_BACK"):
        image_path = tmp_path / f"samples/{channel}/sample-2.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 80)).save(image_path)
    identity = [1, 0, 0, 0]
    _write_table(tmp_path, "sample", [{"token": "sample-1"}, {"token": "sample-2"}])
    _write_table(
        tmp_path,
        "sample_data",
        [
            {
                "token": f"{sample}:{channel}",
                "sample_token": sample,
                "calibrated_sensor_token": channel,
                "ego_pose_token": f"ego-{sample}",
                "filename": f"samples/{channel}/{sample}.jpg",
            }
            for sample in ("sample-1", "sample-2")
            for channel in ("CAM_FRONT", "CAM_BACK")
        ],
    )
    _write_table(
        tmp_path,
        "calibrated_sensor",
        [
            {
                "token": channel,
                "sensor_token": f"sensor-{channel}",
                "translation": [0, 0, 0],
                "rotation": identity,
                "camera_intrinsic": [[100, 0, 50], [0, 100, 40], [0, 0, 1]],
            }
            for channel in ("CAM_FRONT", "CAM_BACK")
        ],
    )
    _write_table(
        tmp_path,
        "ego_pose",
        [
            {"token": "ego-sample-1", "translation": [0, 0, 0], "rotation": identity},
            {"token": "ego-sample-2", "translation": [0, 0, 0], "rotation": identity},
        ],
    )
    _write_table(tmp_path, "category", [])
    _write_table(tmp_path, "sample_annotation", [])

    images, cases = NuScenesAdapter(tmp_path, max_images=1).load()

    assert cases == []
    assert [image.source_image_id for image in images] == ["sample-1:CAM_FRONT", "sample-1:CAM_BACK"]
    assert [image.storage_filename for image in images] == [
        "sample-1/sample-1/CAM_FRONT.jpg",
        "sample-1/sample-1/CAM_BACK.jpg",
    ]


def test_ignores_nuscenes_camera_sweeps_for_synchronized_frame_groups(tmp_path: Path):
    for filename in ("samples/CAM_FRONT/keyframe.jpg", "sweeps/CAM_FRONT/sweep.jpg"):
        image_path = tmp_path / filename
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (100, 80)).save(image_path)
    identity = [1, 0, 0, 0]
    _write_table(tmp_path, "sample", [{"token": "sample-1", "timestamp": 1}])
    _write_table(
        tmp_path,
        "sample_data",
        [
            {
                "token": "camera-keyframe",
                "sample_token": "sample-1",
                "calibrated_sensor_token": "CAM_FRONT",
                "ego_pose_token": "ego-1",
                "filename": "samples/CAM_FRONT/keyframe.jpg",
                "is_key_frame": True,
            },
            {
                "token": "camera-sweep",
                "sample_token": "sample-1",
                "calibrated_sensor_token": "CAM_FRONT",
                "ego_pose_token": "ego-1",
                "filename": "sweeps/CAM_FRONT/sweep.jpg",
                "is_key_frame": False,
            },
        ],
    )
    _write_table(
        tmp_path,
        "calibrated_sensor",
        [
            {
                "token": "CAM_FRONT",
                "sensor_token": "sensor-CAM_FRONT",
                "translation": [0, 0, 0],
                "rotation": identity,
                "camera_intrinsic": [[100, 0, 50], [0, 100, 40], [0, 0, 1]],
            }
        ],
    )
    _write_table(tmp_path, "sensor", [{"token": "sensor-CAM_FRONT", "channel": "CAM_FRONT", "modality": "camera"}])
    _write_table(tmp_path, "ego_pose", [{"token": "ego-1", "translation": [0, 0, 0], "rotation": identity}])
    _write_table(tmp_path, "category", [])
    _write_table(tmp_path, "sample_annotation", [])

    images, cases = NuScenesAdapter(tmp_path).load()

    assert cases == []
    assert [image.source_image_id for image in images] == ["camera-keyframe"]
    assert images[0].storage_filename == "sample-1/sample-1/CAM_FRONT.jpg"
