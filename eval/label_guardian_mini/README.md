# label-guardian-mini

Deterministic synthetic fixture for the Label Guardian CVAT workflow.

- 2 sequences x 6 PNG frames at 1280 x 720.
- Classes: `car`, `pedestrian`, `cyclist`, `traffic_sign`.
- Ground truth in CVAT for images 1.1 XML and COCO JSON.
- Mock predictions with six intentional QA error types.
- QA cases initially contain null Project/Task/Job IDs. The CVAT bootstrap step writes a separate mapping after upload.

Regenerate from the repository root:

```powershell
python -m scripts.label_guardian_generate_fixture
```

The generator draws all geometry at known coordinates. This makes expected bounding boxes and tracks reproducible across local runs and CI.

Bootstrap the fixture to the configured CVAT account after installing the optional SDK group:

```powershell
python -m pip install -e ".[cvat]"
python -m scripts.label_guardian_bootstrap_cvat_fixture
```

The bootstrap is idempotent by the exact project/task names. It never deletes CVAT resources.
