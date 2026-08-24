import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

from src.services.ingestion.kitti_adapter import KittiAdapter
from src.services.ingestion.nuscenes_adapter import NuScenesAdapter
from src.services.ingestion.official_dataset_downloader import (
    DatasetDownloadError,
    KittiEmailInboxConfig,
    _extract_kitti_download_url_from_message,
    _poll_kitti_download_email,
    _safe_extract_tar,
    download_official_kitti_object,
    download_official_nuscenes,
)


def test_safe_tar_extraction_rejects_symbolic_links(tmp_path: Path):
    archive_path = tmp_path / "unsafe.tgz"
    with tarfile.open(archive_path, "w:gz") as archive:
        link = tarfile.TarInfo("dataset/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)

    try:
        _safe_extract_tar(archive_path, tmp_path / "destination")
    except DatasetDownloadError as error:
        assert "Refusing to extract archive link" in str(error)
    else:
        raise AssertionError("Expected symbolic-link tar member to be rejected")


def _write_zip(archive_path: Path, files: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_downloads_official_kitti_archives_from_authenticated_urls(tmp_path: Path):
    image = tmp_path / "000000.png"
    Image.new("RGB", (100, 80), (1, 2, 3)).save(image)
    image_zip = tmp_path / "data_object_image_2.zip"
    velodyne_zip = tmp_path / "data_object_velodyne.zip"
    label_zip = tmp_path / "data_object_label_2.zip"
    calib_zip = tmp_path / "data_object_calib.zip"
    _write_zip(image_zip, {"training/image_2/000000.png": image.read_bytes()})
    _write_zip(velodyne_zip, {"training/velodyne/000000.bin": b""})
    _write_zip(
        label_zip,
        {
            "training/label_2/000000.txt": (
                "Car 0.00 0 -1.57 10.00 20.00 30.00 40.00 1.50 1.60 4.00 1.00 2.00 15.00 0.01\n"
            )
        },
    )
    _write_zip(calib_zip, {"training/calib/000000.txt": "P2: 100 0 50 0 0 100 40 0 0 0 1 0\n"})

    progress_messages: list[str] = []
    downloaded = download_official_kitti_object(
        tmp_path / "raw",
        image_url=f"file://{image_zip}",
        label_url=f"file://{label_zip}",
        calib_url=f"file://{calib_zip}",
        velodyne_url=f"file://{velodyne_zip}",
        progress=progress_messages.append,
    )
    images, cases = KittiAdapter(downloaded.dataset_root).load()

    assert downloaded.dataset_root == tmp_path / "raw" / "kitti_object"
    assert any("Preparing KITTI archive" in message for message in progress_messages)
    assert any("Extracting KITTI archive" in message for message in progress_messages)
    assert images[0].filename == "training/image_2/000000.png"
    assert cases[0].provenance[0].source_annotation_id == "000000:0"


def test_kitti_download_reports_html_email_page(tmp_path: Path):
    html = tmp_path / "not-a-zip.html"
    html.write_text("<html>Please enter your email address to download</html>")

    try:
        download_official_kitti_object(
            tmp_path / "raw",
            image_url=f"file://{html}",
            velodyne_url=f"file://{html}",
            label_url=f"file://{html}",
            calib_url=f"file://{html}",
        )
    except DatasetDownloadError as error:
        assert "HTML login/email page" in str(error)
        assert (tmp_path / "raw" / "diagnostics" / "data_object_image_2.zip.html").is_file()
    else:
        raise AssertionError("Expected KITTI HTML response to fail as invalid archive")


def test_kitti_download_validates_cookie_file(tmp_path: Path):
    try:
        download_official_kitti_object(tmp_path / "raw", cookie_file=tmp_path / "missing-cookie.txt")
    except DatasetDownloadError as error:
        assert "cookie file does not exist" in str(error)
    else:
        raise AssertionError("Expected missing KITTI cookie file to fail")


def test_downloads_official_nuscenes_mini_archive(tmp_path: Path):
    archive_root = tmp_path / "archive_root"
    metadata_root = archive_root / "v1.0-mini"
    sample_root = archive_root / "samples" / "CAM_FRONT"
    metadata_root.mkdir(parents=True)
    sample_root.mkdir(parents=True)
    Image.new("RGB", (1600, 900), (10, 20, 30)).save(sample_root / "sample.jpg")
    (metadata_root / "sample.json").write_text(json.dumps([{"token": "sample-token"}]))
    (metadata_root / "sample_data.json").write_text(
        json.dumps(
            [
                {
                    "token": "camera-token",
                    "sample_token": "sample-token",
                    "ego_pose_token": "ego-pose-token",
                    "calibrated_sensor_token": "camera-calibration-token",
                    "filename": "samples/CAM_FRONT/sample.jpg",
                }
            ]
        )
    )
    (metadata_root / "sample_annotation.json").write_text(
        json.dumps(
            [
                {
                    "token": "annotation-token",
                    "sample_token": "sample-token",
                    "category_token": "category-token",
                    "translation": [0, 0, 20],
                    "size": [2, 4, 2],
                    "rotation": [1, 0, 0, 0],
                }
            ]
        )
    )
    (metadata_root / "calibrated_sensor.json").write_text(
        json.dumps(
            [
                {
                    "token": "camera-calibration-token",
                    "sensor_token": "camera-sensor-token",
                    "translation": [0, 0, 0],
                    "rotation": [1, 0, 0, 0],
                    "camera_intrinsic": [[1000, 0, 800], [0, 1000, 450], [0, 0, 1]],
                }
            ]
        )
    )
    (metadata_root / "ego_pose.json").write_text(
        json.dumps([{"token": "ego-pose-token", "translation": [0, 0, 0], "rotation": [1, 0, 0, 0]}])
    )
    (metadata_root / "category.json").write_text(json.dumps([{"token": "category-token", "name": "vehicle.car"}]))
    archive_path = tmp_path / "v1.0-mini.tgz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(metadata_root, arcname="v1.0-mini")
        archive.add(sample_root, arcname="samples/CAM_FRONT")

    downloaded = download_official_nuscenes(tmp_path / "raw", url=f"file://{archive_path}")
    images, cases = NuScenesAdapter(downloaded.dataset_root).load()

    assert downloaded.dataset_root == tmp_path / "raw" / "nuscenes"
    assert images[0].filename == "samples/CAM_FRONT/sample.jpg"
    assert cases[0].label == "vehicle.car"


def test_nuscenes_download_replaces_truncated_cached_archive(tmp_path: Path):
    archive_root = tmp_path / "archive_root"
    metadata_root = archive_root / "v1.0-mini"
    metadata_root.mkdir(parents=True)
    for table in ("sample", "sample_data", "sample_annotation", "calibrated_sensor", "ego_pose", "category"):
        (metadata_root / f"{table}.json").write_text(json.dumps([]))
    valid_archive = tmp_path / "valid-mini.tgz"
    with tarfile.open(valid_archive, "w:gz") as archive:
        archive.add(metadata_root, arcname="v1.0-mini")
    cached_archive = tmp_path / "raw" / "archives" / valid_archive.name
    cached_archive.parent.mkdir(parents=True)
    cached_archive.write_bytes(b"truncated gzip content")
    progress_messages: list[str] = []

    downloaded = download_official_nuscenes(
        tmp_path / "raw",
        url=f"file://{valid_archive}",
        progress=progress_messages.append,
    )

    assert downloaded.downloaded_files == [cached_archive]
    assert any("Cached archive is invalid" in message for message in progress_messages)
    assert cached_archive.stat().st_size == valid_archive.stat().st_size


def test_kitti_download_requests_email_link_for_html_response(tmp_path: Path, monkeypatch):
    html = tmp_path / "not-a-zip.html"
    html.write_text("<html>Please enter your email address to download</html>")
    calls: list[urllib.request.Request] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"<html>Email sent</html>"

    def fake_urlopen(request, timeout=120):
        del timeout
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    try:
        download_official_kitti_object(
            tmp_path / "raw",
            image_url=f"file://{html}",
            velodyne_url=f"file://{html}",
            label_url=f"file://{html}",
            calib_url=f"file://{html}",
            kitti_email="qa@example.test",
        )
    except DatasetDownloadError as error:
        assert "A request was submitted to qa@example.test" in str(error)
    else:
        raise AssertionError("Expected KITTI HTML response to trigger email request and fail pending inbox link")

    assert calls
    assert (tmp_path / "raw" / "diagnostics" / "data_object_image_2.zip.request.html").is_file()


def test_extracts_kitti_direct_url_from_cvlibs_email_message():
    raw = b"""From: cvlibs@example.test\nContent-Type: text/html; charset=utf-8\n\n<html><body><a href=\"https://www.cvlibs.net/download.php?file=data_object_image_2.zip&amp;token=abc\">download</a></body></html>"""

    assert _extract_kitti_download_url_from_message(raw, "data_object_image_2.zip") == (
        "https://www.cvlibs.net/download.php?file=data_object_image_2.zip&token=abc"
    )


def test_extracts_kitti_s3_url_from_cvlibs_delivery_email():
    raw = b"""From: cvlibs@example.test\n\nLink to download: https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_image_2.zip\n"""

    assert _extract_kitti_download_url_from_message(raw, "data_object_image_2.zip") == (
        "https://s3.eu-central-1.amazonaws.com/avg-kitti/data_object_image_2.zip"
    )


def test_kitti_download_continues_after_polling_emailed_direct_url(tmp_path: Path, monkeypatch):
    html = tmp_path / "request-page.html"
    html.write_text("<html>Please enter your email address to download</html>")
    archive = tmp_path / "data_object_image_2.zip"
    _write_zip(archive, {"training/image_2/000000.png": b"image"})
    direct_urls = {
        "data_object_image_2.zip": f"file://{archive}",
        "data_object_velodyne.zip": f"file://{archive}",
        "data_object_label_2.zip": f"file://{archive}",
        "data_object_calib.zip": f"file://{archive}",
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"<html>Email sent</html>"

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=120: FakeResponse())
    monkeypatch.setattr(
        "src.services.ingestion.official_dataset_downloader._poll_kitti_download_email",
        lambda archive_name, config, progress: direct_urls[archive_name],
    )

    downloaded = download_official_kitti_object(
        tmp_path / "raw",
        image_url=f"file://{html}",
        velodyne_url=f"file://{html}",
        label_url=f"file://{html}",
        calib_url=f"file://{html}",
        kitti_email="qa@example.test",
        kitti_inbox=KittiEmailInboxConfig(
            host="imap.example.test", username="qa@example.test", password="app-password"
        ),
    )

    assert downloaded.dataset_root.is_dir()
    assert len(downloaded.downloaded_files) == 4


def test_kitti_imap_connection_error_is_actionable(monkeypatch):
    def fail_connection(host):
        raise OSError("name resolution failed")

    monkeypatch.setattr("imaplib.IMAP4_SSL", fail_connection)

    try:
        _poll_kitti_download_email(
            "data_object_image_2.zip",
            KittiEmailInboxConfig(host="not-an-imap-host", username="qa@example.test", password="app-password"),
            None,
        )
    except DatasetDownloadError as error:
        assert "Cannot reach KITTI delivery mailbox at not-an-imap-host" in str(error)
        assert "port 993" in str(error)
