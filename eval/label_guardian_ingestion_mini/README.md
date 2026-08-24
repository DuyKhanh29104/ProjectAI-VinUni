# Label Guardian ingestion mini fixture

This deterministic fixture exercises the offline data-foundation ingestion flow.
It contains 12 100x80 PNG frames (`000000.png` through `000011.png`), paired
KITTI calibration files, and equivalent COCO/CVAT annotations.

It is intentionally separate from `eval/label_guardian_mini`, which remains the
canonical CVAT QA evaluation fixture used by the existing application tests.
