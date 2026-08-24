import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.config import IngestionSettings
from src.db.base import Base
from src.models.ingestion import QAImage
from src.services.ingestion.cloud_worker import CloudIngestionRequest, CloudIngestionWorker
from src.services.ingestion.kitti_adapter import ImageMetadata, KittiAdapter
from src.services.ingestion.local_storage import LocalObjectStorageClient


def _write_zip(archive_path: Path, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _write_tar(archive_path: Path, files: dict[str, bytes | str]) -> None:
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _stage_kitti_raw_archives(tmp_path: Path, storage: LocalObjectStorageClient, bucket: str) -> None:
    image = tmp_path / "000000.png"
    Image.new("RGB", (100, 80), (1, 2, 3)).save(image)
    archive_payloads = {
        "data_object_image_2.zip": {"training/image_2/000000.png": image.read_bytes()},
        "data_object_velodyne.zip": {"training/velodyne/000000.bin": b"velodyne"},
        "data_object_label_2.zip": {
            "training/label_2/000000.txt": (
                "Car 0.00 0 -1.57 10.00 20.00 30.00 40.00 1.50 1.60 4.00 1.00 2.00 15.00 0.01\n"
            )
        },
        "data_object_calib.zip": {"training/calib/000000.txt": "P2: 100 0 50 0 0 100 40 0 0 0 1 0\n"},
    }
    for archive_name, files in archive_payloads.items():
        archive_path = tmp_path / archive_name
        _write_zip(archive_path, files)
        storage.upload_file(
            str(archive_path),
            bucket,
            f"raw/official/kitti/object/archives/{archive_name}",
            ExtraArgs={"ContentType": "application/zip"},
        )


def _stage_multi_frame_kitti_raw_archives(tmp_path: Path, storage: LocalObjectStorageClient, bucket: str) -> None:
    image_0 = tmp_path / "000000.png"
    image_1 = tmp_path / "000001.png"
    Image.new("RGB", (100, 80), (1, 2, 3)).save(image_0)
    Image.new("RGB", (100, 80), (4, 5, 6)).save(image_1)
    archive_payloads = {
        "data_object_image_2.zip": {
            "training/image_2/000000.png": image_0.read_bytes(),
            "training/image_2/000001.png": image_1.read_bytes(),
        },
        "data_object_velodyne.zip": {
            "training/velodyne/000000.bin": b"velodyne-0",
            "training/velodyne/000001.bin": b"velodyne-1",
        },
        "data_object_label_2.zip": {
            "training/label_2/000000.txt": (
                "Car 0.00 0 -1.57 10.00 20.00 30.00 40.00 1.50 1.60 4.00 1.00 2.00 15.00 0.01\n"
            ),
            "training/label_2/000001.txt": (
                "Car 0.00 0 -1.57 11.00 21.00 31.00 41.00 1.50 1.60 4.00 1.00 2.00 15.00 0.01\n"
            ),
        },
        "data_object_calib.zip": {
            "training/calib/000000.txt": "P2: 100 0 50 0 0 100 40 0 0 0 1 0\n",
            "training/calib/000001.txt": "P2: 100 0 50 0 0 100 40 0 0 0 1 0\n",
        },
    }
    for archive_name, files in archive_payloads.items():
        archive_path = tmp_path / archive_name
        _write_zip(archive_path, files)
        storage.upload_file(
            str(archive_path),
            bucket,
            f"raw/official/kitti/object/archives/{archive_name}",
            ExtraArgs={"ContentType": "application/zip"},
        )


def _stage_nuscenes_trainval_archives(tmp_path: Path, storage: LocalObjectStorageClient, bucket: str) -> None:
    identity = [1, 0, 0, 0]
    camera_channels = (
        "CAM_FRONT",
        "CAM_FRONT_RIGHT",
        "CAM_BACK_RIGHT",
        "CAM_BACK",
        "CAM_BACK_LEFT",
        "CAM_FRONT_LEFT",
    )
    image_bytes: dict[str, bytes] = {}
    for sample_token in ("sample-1", "sample-2"):
        for channel in camera_channels:
            image_path = tmp_path / f"{sample_token}-{channel}.jpg"
            Image.new("RGB", (100, 80), (10, 20, 30)).save(image_path)
            image_bytes[f"samples/{channel}/{sample_token}.jpg"] = image_path.read_bytes()
    image_bytes["samples/LIDAR_TOP/sample-1.pcd.bin"] = b"lidar-sample-1"
    image_bytes["samples/LIDAR_TOP/sample-2.pcd.bin"] = b"lidar-sample-2"
    samples = [
        {"token": "sample-1", "timestamp": 1, "scene_token": "scene-token"},
        {"token": "sample-2", "timestamp": 2, "scene_token": "scene-token"},
    ]
    sensors = [
        {"token": f"sensor-{channel}", "channel": channel, "modality": "camera"}
        for channel in camera_channels
    ] + [{"token": "sensor-LIDAR_TOP", "channel": "LIDAR_TOP", "modality": "lidar"}]
    calibrated_sensor = [
        {
            "token": f"calib-{channel}",
            "sensor_token": f"sensor-{channel}",
            "translation": [0, 0, 0],
            "rotation": identity,
            "camera_intrinsic": [[100, 0, 50], [0, 100, 40], [0, 0, 1]],
        }
        for channel in camera_channels
    ] + [
        {
            "token": "calib-LIDAR_TOP",
            "sensor_token": "sensor-LIDAR_TOP",
            "translation": [0, 0, 0],
            "rotation": identity,
        }
    ]
    sample_data = []
    for sample_token in ("sample-1", "sample-2"):
        for channel in camera_channels:
            sample_data.append(
                {
                    "token": f"{sample_token}:{channel}",
                    "sample_token": sample_token,
                    "calibrated_sensor_token": f"calib-{channel}",
                    "ego_pose_token": f"ego-{sample_token}",
                    "filename": f"samples/{channel}/{sample_token}.jpg",
                    "is_key_frame": True,
                }
            )
        sample_data.append(
            {
                "token": f"{sample_token}:LIDAR_TOP",
                "sample_token": sample_token,
                "calibrated_sensor_token": "calib-LIDAR_TOP",
                "ego_pose_token": f"ego-{sample_token}",
                "filename": f"samples/LIDAR_TOP/{sample_token}.pcd.bin",
                "is_key_frame": True,
            }
        )
    metadata_files = {
        "v1.0-trainval/sample.json": json.dumps(samples),
        "v1.0-trainval/sample_data.json": json.dumps(sample_data),
        "v1.0-trainval/sample_annotation.json": json.dumps(
            [
                {
                    "token": "annotation-1",
                    "sample_token": "sample-1",
                    "category_name": "vehicle.car",
                    "translation": [0, 0, 10],
                    "size": [2, 2, 2],
                    "rotation": identity,
                }
            ]
        ),
        "v1.0-trainval/calibrated_sensor.json": json.dumps(calibrated_sensor),
        "v1.0-trainval/ego_pose.json": json.dumps(
            [
                {"token": "ego-sample-1", "translation": [0, 0, 0], "rotation": identity},
                {"token": "ego-sample-2", "translation": [0, 0, 0], "rotation": identity},
            ]
        ),
        "v1.0-trainval/category.json": json.dumps([]),
        "v1.0-trainval/scene.json": json.dumps([{"token": "scene-token", "name": "scene-0001"}]),
        "v1.0-trainval/sensor.json": json.dumps(sensors),
    }
    meta_archive = tmp_path / "v1.0-trainval_meta.tgz"
    _write_tar(meta_archive, metadata_files)
    storage.upload_file(
        str(meta_archive),
        bucket,
        "raw/official/nuscenes/v1.0-trainval/archives/v1.0-trainval_meta.tgz",
        ExtraArgs={"ContentType": "application/gzip"},
    )
    for index in range(1, 11):
        archive_name = f"v1.0-trainval{index:02d}_blobs.tgz"
        archive_path = tmp_path / archive_name
        _write_tar(archive_path, image_bytes if index == 1 else {})
        storage.upload_file(
            str(archive_path),
            bucket,
            f"raw/official/nuscenes/v1.0-trainval/archives/{archive_name}",
            ExtraArgs={"ContentType": "application/gzip"},
        )


def test_official_kitti_adapter_emits_canonical_cloud_frame_path(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_kitti_raw_archives(tmp_path, storage, "bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")
    dataset_root = worker._materialize_raw_dataset(request)

    images, _ = KittiAdapter(dataset_root).load()

    assert images[0].storage_filename == "sequence-default/000000/CAM_FRONT.png"
    assert not (dataset_root / "training" / "velodyne").exists()


def test_cloud_worker_normalizes_kitti_raw_archives_from_gcs_style_storage(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_kitti_raw_archives(tmp_path, storage, "bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")

    worker.normalize_to_staging(request)
    report = worker.validate(request)

    frame_key = (
        "datasets/staging/run/official/kitti/object/smoke/frames/"
        "sequence-default/000000/CAM_FRONT.png"
    )
    manifest_key = "datasets/staging/run/official/kitti/object/smoke/manifests/ingest_manifest.json"
    assert storage.object_exists("bucket", frame_key)
    assert storage.object_exists("bucket", manifest_key)
    assert report.passed is True
    assert report.images == 1
    assert report.objects == 1
    assert report.frame_groups == {"sequence-default/000000": 1}


def test_cloud_worker_normalizes_kitti_lidar_artifacts_for_3d_smoke(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_kitti_raw_archives(tmp_path, storage, "bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(
        dataset_type="kitti",
        release="object",
        split="smoke",
        max_frames=1,
        run_id="run-3d",
        modalities=["camera", "labels", "calibration", "lidar"],
    )

    worker.normalize_to_staging(request)
    report = worker.validate(request)

    assert storage.object_exists(
        "bucket",
        "datasets/staging/run-3d/official/kitti/object/smoke/pointclouds/sequence-default/000000/LIDAR_TOP.bin",
    )
    assert storage.object_exists(
        "bucket",
        "datasets/staging/run-3d/official/kitti/object/smoke/calibration/sequence-default/000000/calib.txt",
    )
    assert report.passed is True
    assert report.pointclouds == 1
    assert report.calibration_files == 1


def test_cloud_worker_streams_only_selected_kitti_frames_without_archive_materialization(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_multi_frame_kitti_raw_archives(tmp_path, storage, "bucket")
    scratch_root = tmp_path / "scratch"
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=scratch_root,
    )
    request = CloudIngestionRequest(
        dataset_type="kitti",
        release="object",
        split="smoke",
        max_frames=1,
        run_id="run-streamed",
        modalities=["camera", "labels", "calibration", "lidar"],
    )

    dataset_root = worker._materialize_raw_dataset(request)

    assert (dataset_root / "training" / "image_2" / "000000.png").is_file()
    assert not (dataset_root / "training" / "image_2" / "000001.png").exists()
    assert (dataset_root / "training" / "velodyne" / "000000.bin").is_file()
    assert not (dataset_root / "training" / "velodyne" / "000001.bin").exists()
    assert not list((scratch_root / "run-streamed").glob("archives/*.zip"))


def test_cloud_worker_normalizes_nuscenes_trainval_multi_archive_with_lidar(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_nuscenes_trainval_archives(tmp_path, storage, "bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(
        dataset_type="nuscenes",
        release="v1.0-trainval",
        split="smoke",
        max_frames=1,
        run_id="nuscenes-trainval-smoke",
        modalities=["camera", "labels", "calibration", "lidar"],
    )

    worker.normalize_to_staging(request)
    report = worker.validate(request)

    assert report.passed is True
    assert report.images == 6
    assert report.pointclouds == 1
    assert report.calibration_files == 1
    assert report.frame_groups == {"scene-0001/sample-1": 6}
    assert storage.object_exists(
        "bucket",
        "datasets/staging/nuscenes-trainval-smoke/official/nuscenes/v1.0-trainval/smoke/"
        "frames/scene-0001/sample-1/CAM_FRONT.jpg",
    )
    assert storage.object_exists(
        "bucket",
        "datasets/staging/nuscenes-trainval-smoke/official/nuscenes/v1.0-trainval/smoke/"
        "pointclouds/scene-0001/sample-1/LIDAR_TOP.pcd.bin",
    )
    assert not (tmp_path / "scratch" / "nuscenes-trainval-smoke" / "dataset" / "nuscenes" / "samples" / "CAM_FRONT" / "sample-2.jpg").exists()


def test_cloud_worker_rejects_missing_gcs_raw_archives(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")

    with pytest.raises(RuntimeError, match="Missing raw archive in GCS"):
        worker.normalize_to_staging(request)


def test_cloud_worker_stage_requires_kitti_secret_urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("KITTI_IMAGE_2_URL", "KITTI_LABEL_2_URL", "KITTI_CALIB_URL", "KITTI_VELODYNE_URL"):
        monkeypatch.delenv(name, raising=False)
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")

    with pytest.raises(RuntimeError, match="Missing official source URL"):
        worker.stage_raw(request)


def test_cloud_worker_2d_kitti_stage_does_not_require_lidar_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("KITTI_IMAGE_2_URL", "KITTI_LABEL_2_URL", "KITTI_CALIB_URL", "KITTI_VELODYNE_URL"):
        monkeypatch.delenv(name, raising=False)
    for archive_name in ("data_object_image_2.zip", "data_object_label_2.zip", "data_object_calib.zip"):
        monkeypatch.setenv(f"KITTI_{archive_name.removeprefix('data_object_').removesuffix('.zip').upper()}_URL", f"file:///{archive_name}")
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")

    assert "data_object_velodyne.zip" not in worker.raw_archive_keys(request)


def test_cloud_worker_lidar_request_includes_velodyne_archive(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(
        dataset_type="kitti",
        release="object",
        split="smoke",
        max_frames=1,
        run_id="run-3d",
        modalities=["camera", "labels", "calibration", "lidar"],
    )

    assert "data_object_velodyne.zip" in worker.raw_archive_keys(request)


def test_cloud_worker_can_limit_nuscenes_trainval_blob_archives_for_smoke(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )

    smoke_request = CloudIngestionRequest(
        dataset_type="nuscenes",
        release="v1.0-trainval",
        split="smoke",
        max_frames=5,
        max_blob_archives=1,
        run_id="nuscenes-smoke",
    )
    full_request = CloudIngestionRequest(
        dataset_type="nuscenes",
        release="v1.0-trainval",
        split="train",
        run_id="nuscenes-full",
    )

    assert list(worker.raw_archive_keys(smoke_request)) == [
        "v1.0-trainval_meta.tgz",
        "v1.0-trainval01_blobs.tgz",
    ]
    assert len(worker.raw_archive_keys(full_request)) == 11


def test_cloud_worker_flags_invalid_nuscenes_camera_view_sets() -> None:
    images = [
        ImageMetadata("front", "samples/CAM_FRONT/keyframe.jpg", 100, 80, storage_filename="scene/sample/CAM_FRONT.jpg"),
        ImageMetadata("extra", "sweeps/CAM_FRONT/sweep.jpg", 100, 80, storage_filename="scene/sample/CAM_FRONT_SWEEP.jpg"),
    ]

    invalid = CloudIngestionWorker._invalid_nuscenes_camera_sets(images)

    assert invalid == {"scene/sample": ["CAM_FRONT", "CAM_FRONT_SWEEP"]}


def test_cloud_worker_publish_copies_staging_to_canonical_without_database(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_kitti_raw_archives(tmp_path, storage, "bucket")
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(dataset_type="kitti", release="object", split="smoke", max_frames=1, run_id="run")

    worker.normalize_to_staging(request)
    worker.publish(request)

    canonical_key = (
        "datasets/official/kitti/object/smoke/frames/"
        "sequence-default/000000/CAM_FRONT.png"
    )
    result_key = "ops/ingestion-runs/run/result.json"
    assert storage.object_exists("bucket", canonical_key)
    assert json.loads((tmp_path / "objects" / "bucket" / result_key).read_text())["published"] is True


def test_cloud_worker_publish_removes_stale_database_frames_for_canonical_prefix(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    request = CloudIngestionRequest(
        dataset_type="nuscenes",
        release="v1.0-mini",
        split="smoke",
        max_frames=1,
        run_id="nuscenes-smoke",
    )
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=LocalObjectStorageClient(tmp_path / "objects"),
        session_factory=session_factory,
        scratch_root=tmp_path / "scratch",
    )
    canonical_prefix = worker.canonical_prefix(request)
    with session_factory() as session, session.begin():
        session.add_all(
            [
                QAImage(
                    source_image_id="stale-camera",
                    filename="samples/CAM_FRONT/stale.jpg",
                    width=100,
                    height=80,
                    object_url="gs://bucket/stale",
                    provider="nuscenes",
                    dataset="nuscenes",
                    release="v1.0-mini",
                    modality="camera",
                    asset_type="image",
                    data_format="jpg",
                    storage_key=f"{canonical_prefix}/frames/sweeps/old/CAM_FRONT.jpg",
                ),
                QAImage(
                    source_image_id="other-split-camera",
                    filename="samples/CAM_FRONT/other.jpg",
                    width=100,
                    height=80,
                    object_url="gs://bucket/other",
                    provider="nuscenes",
                    dataset="nuscenes",
                    release="v1.0-mini",
                    modality="camera",
                    asset_type="image",
                    data_format="jpg",
                    storage_key="datasets/official/nuscenes/v1.0-mini/val/frames/scene/other/CAM_FRONT.jpg",
                ),
            ]
        )

    worker._persist_metadata(
        request,
        [
            ImageMetadata(
                source_image_id="fresh-camera",
                filename="samples/CAM_FRONT/fresh.jpg",
                width=100,
                height=80,
                storage_filename="scene-0001/sample-1/CAM_FRONT.jpg",
            )
        ],
        [],
    )

    with session_factory() as session:
        rows = session.scalars(select(QAImage).order_by(QAImage.source_image_id)).all()

    assert [row.source_image_id for row in rows] == ["fresh-camera", "other-split-camera"]
    assert rows[0].storage_key == f"{canonical_prefix}/frames/scene-0001/sample-1/CAM_FRONT.jpg"


def test_cloud_worker_publish_resume_still_syncs_database_metadata(tmp_path: Path) -> None:
    storage = LocalObjectStorageClient(tmp_path / "objects")
    storage.create_bucket(Bucket="bucket")
    _stage_kitti_raw_archives(tmp_path, storage, "bucket")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    worker = CloudIngestionWorker(
        settings=IngestionSettings(gcs_bucket="bucket", _env_file=None),
        storage_client=storage,
        session_factory=session_factory,
        scratch_root=tmp_path / "scratch",
    )
    request = CloudIngestionRequest(
        dataset_type="kitti",
        release="object",
        split="full",
        run_id="kitti-full",
        modalities=["camera", "labels", "calibration", "lidar"],
    )
    worker.normalize_to_staging(request)
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"published": True}), encoding="utf-8")
    storage.upload_file(
        str(result_path),
        "bucket",
        "ops/ingestion-runs/kitti-full/result.json",
        ExtraArgs={"ContentType": "application/json"},
    )

    worker.publish(request)

    with session_factory() as session:
        rows = session.scalars(select(QAImage)).all()

    assert len(rows) == 1
    assert rows[0].source_image_id == "kitti:000000"
    assert rows[0].storage_key == "datasets/official/kitti/object/full/frames/sequence-default/000000/CAM_FRONT.png"
