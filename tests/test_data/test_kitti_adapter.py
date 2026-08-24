import json
from pathlib import Path

from PIL import Image

from src.models.ingestion import AnnotationSource, QAReviewStatus
from src.services.ingestion.kitti_adapter import KittiAdapter, parse_kitti_calibration

KITTI_CALIBRATION = "P2: 100 0 50 0 0 100 40 0 0 0 1 0\nTr_velo_to_cam: 1 0 0 0 0 1 0 0 0 0 1 0\n"


def _write_fixture(root: Path) -> None:
    (root / "calib").mkdir(parents=True)
    (root / "calib" / "000000.txt").write_text(KITTI_CALIBRATION)
    (root / "annotations.coco.json").write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": "000000.png", "width": 100, "height": 80}],
                "categories": [{"id": 1, "name": "car"}],
                "annotations": [
                    {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 20, 20]},
                    {"id": 2, "image_id": 1, "category_id": 1, "bbox": [60, 10, 20, 20]},
                ],
            }
        )
    )


def test_parses_kitti_calibration(tmp_path: Path):
    _write_fixture(tmp_path)
    calibration = parse_kitti_calibration(tmp_path / "calib" / "000000.txt")
    assert calibration["P2"] == [[100.0, 0.0, 50.0, 0.0], [0.0, 100.0, 40.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    assert calibration["Tr_velo_to_cam"][2][2] == 1.0


def test_loads_coco_annotations(tmp_path: Path):
    _write_fixture(tmp_path)
    images, cases = KittiAdapter(tmp_path).load()
    assert images[0].filename == "000000.png"
    assert [case.review_status for case in cases] == [QAReviewStatus.VERIFIED, QAReviewStatus.VERIFIED]
    assert len(cases[0].provenance) == 1
    assert len(cases[1].provenance) == 1
    assert cases[0].calibration["P2"][0][0] == 100.0


def test_committed_mini_fixture_has_twelve_images_and_calibrations():
    fixture_root = Path("eval/label_guardian_ingestion_mini")
    assert len(list(fixture_root.glob("*.png"))) == 12
    assert len(list((fixture_root / "calib").glob("*.txt"))) == 12
    images, cases = KittiAdapter(fixture_root).load()
    assert len(images) == 12
    assert cases[0].review_status == QAReviewStatus.VERIFIED


def test_parses_official_kitti_object_layout(tmp_path: Path):
    (tmp_path / "training" / "image_2").mkdir(parents=True)
    (tmp_path / "training" / "label_2").mkdir(parents=True)
    (tmp_path / "training" / "calib").mkdir(parents=True)
    Image.new("RGB", (1242, 375), (10, 20, 30)).save(tmp_path / "training" / "image_2" / "000000.png")
    (tmp_path / "training" / "calib" / "000000.txt").write_text(KITTI_CALIBRATION)
    (tmp_path / "training" / "label_2" / "000000.txt").write_text(
        "Car 0.00 0 -1.57 10.00 20.00 110.00 220.00 1.50 1.60 4.00 1.00 2.00 15.00 0.01\n"
        "DontCare -1 -1 -10 0.00 0.00 5.00 5.00 -1 -1 -1 -1000 -1000 -1000 -10\n"
    )

    images, cases = KittiAdapter(tmp_path).load()

    assert images[0].source_image_id == "kitti:000000"
    assert images[0].filename == "training/image_2/000000.png"
    assert images[0].width == 1242
    assert len(cases) == 1
    assert cases[0].label == "car"
    assert cases[0].bbox.as_xyxy() == [10.0, 20.0, 110.0, 220.0]
    assert cases[0].review_status == QAReviewStatus.VERIFIED
    assert cases[0].provenance[0].source == AnnotationSource.KITTI
    assert cases[0].calibration["P2"][0][0] == 100.0
