import numpy as np
import pytest

from src.services.ingestion.nuscenes_adapter import project_cuboid_to_bbox, project_cuboid_to_qa_object


@pytest.fixture
def cuboid() -> np.ndarray:
    return np.array(
        [
            [-1, -1, 10],
            [1, -1, 10],
            [1, 1, 10],
            [-1, 1, 10],
            [-1, -1, 12],
            [1, -1, 12],
            [1, 1, 12],
            [-1, 1, 12],
        ]
    )


@pytest.fixture
def intrinsic() -> np.ndarray:
    return np.array([[100, 0, 50], [0, 100, 40], [0, 0, 1]])


def test_projects_mock_cuboid_to_known_pixels(cuboid: np.ndarray, intrinsic: np.ndarray):
    bbox = project_cuboid_to_bbox(cuboid, np.eye(4), intrinsic)
    assert bbox is not None
    assert bbox.as_xyxy() == [40.0, 30.0, 60.0, 50.0]


def test_applies_extrinsic_before_projection(cuboid: np.ndarray, intrinsic: np.ndarray):
    extrinsic = np.eye(4)
    extrinsic[0, 3] = 1
    bbox = project_cuboid_to_bbox(cuboid, extrinsic, intrinsic)
    assert bbox is not None
    assert bbox.xmin == pytest.approx(50.0)
    assert bbox.xmax == pytest.approx(70.0)


def test_returns_none_when_cuboid_is_behind_camera(cuboid: np.ndarray, intrinsic: np.ndarray):
    extrinsic = np.eye(4)
    extrinsic[2, 3] = -20
    assert project_cuboid_to_bbox(cuboid, extrinsic, intrinsic) is None


def test_maps_projection_to_qa_object(cuboid: np.ndarray, intrinsic: np.ndarray):
    qa_object = project_cuboid_to_qa_object(
        source_image_id="1",
        label="car",
        corners=cuboid,
        extrinsic=np.eye(4),
        intrinsic=intrinsic,
        source_annotation_id="sample-1",
    )
    assert qa_object is not None
    assert qa_object.bbox.as_xyxy() == [40.0, 30.0, 60.0, 50.0]
    assert qa_object.cuboid_corners == cuboid.tolist()
    assert qa_object.calibration["extrinsic"] == np.eye(4).tolist()


@pytest.mark.parametrize(
    ("corners", "extrinsic", "intrinsic", "message"),
    [
        (np.zeros((7, 3)), np.eye(4), np.eye(3), "corners"),
        (np.zeros((8, 3)), np.eye(3), np.eye(3), "extrinsic"),
        (np.zeros((8, 3)), np.eye(4), np.eye(4), "intrinsic"),
    ],
)
def test_rejects_invalid_calibration_shapes(corners, extrinsic, intrinsic, message):
    with pytest.raises(ValueError, match=message):
        project_cuboid_to_bbox(corners, extrinsic, intrinsic)
