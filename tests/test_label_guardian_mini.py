import json
from pathlib import Path

from PIL import Image

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "eval" / "label_guardian_mini"


def read_json(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_fixture_has_expected_sequences_frames_and_image_dimensions() -> None:
    manifest = read_json("manifest.json")

    assert manifest["sequenceCount"] == 2
    assert manifest["totalFrames"] == 12
    assert manifest["imageWidth"] == 1280
    assert manifest["imageHeight"] == 720

    for sequence_id in ("seq-001", "seq-002"):
        images = sorted((FIXTURE_ROOT / "sequences" / sequence_id / "images").glob("*.png"))
        assert len(images) == 6
        with Image.open(images[0]) as image:
            assert image.size == (1280, 720)
            assert image.mode == "RGB"


def test_fixture_contains_six_intentional_qa_cases() -> None:
    qa_cases = read_json("qa_cases.json")["cases"]

    assert len(qa_cases) == 6
    assert {case["errorType"] for case in qa_cases} == {
        "box_misalignment",
        "wrong_class",
        "missing_object",
        "duplicate_annotation",
        "track_id_switch",
        "track_break",
    }
    assert all(case["sequenceId"] in {"seq-001", "seq-002"} for case in qa_cases)


def test_all_coco_boxes_stay_inside_the_image() -> None:
    for sequence_id in ("seq-001", "seq-002"):
        coco = json.loads(
            (FIXTURE_ROOT / "sequences" / sequence_id / "coco_instances.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(coco["images"]) == 6
        assert len(coco["annotations"]) == 30
        for annotation in coco["annotations"]:
            x, y, width, height = annotation["bbox"]
            assert x >= 0 and y >= 0
            assert width > 0 and height > 0
            assert x + width <= 1280
            assert y + height <= 720
