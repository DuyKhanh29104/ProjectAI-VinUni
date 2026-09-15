"""Create controlled source annotations and a pending-review golden manifest.

This utility mutates exactly one aspect of each gold annotation according to a
reviewable plan. Generated samples remain excluded from metrics until a human
sets ``review_status`` to ``approved`` and ``use_for_metric`` to ``true``.
"""

from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

ISSUE_ACTIONS = {
    "wrong_class": "change_class",
    "missing_label": "add_label",
    "extra_or_wrong_label": "delete_label",
    "bbox_misaligned": "manual_edit_bbox",
    "duplicate_label": "merge_or_delete_duplicate",
    "clean_no_issue": "no_action",
}

ISSUE_TAGS = {
    "wrong_class": "class_changed",
    "missing_label": "label_removed",
    "extra_or_wrong_label": "background_false_label",
    "bbox_misaligned": "bbox_shifted",
    "duplicate_label": "high_overlap_duplicate",
    "clean_no_issue": "clean",
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _bbox(label: dict[str, Any]) -> dict[str, float]:
    value = label.get("bbox")
    if not isinstance(value, dict):
        raise ValueError(f"Label {label.get('label_id')!r} has no bbox object")
    try:
        return {key: float(value[key]) for key in ("x1", "y1", "x2", "y2")}
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Label {label.get('label_id')!r} has an invalid bbox") from error


def _iou(first: dict[str, float], second: dict[str, float]) -> float:
    intersection_width = max(0.0, min(first["x2"], second["x2"]) - max(first["x1"], second["x1"]))
    intersection_height = max(0.0, min(first["y2"], second["y2"]) - max(first["y1"], second["y1"]))
    intersection = intersection_width * intersection_height
    first_area = (first["x2"] - first["x1"]) * (first["y2"] - first["y1"])
    second_area = (second["x2"] - second["x1"]) * (second["y2"] - second["y1"])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def _translated_bbox(
    bbox: dict[str, float],
    *,
    image_width: int,
    image_height: int,
    dx: float,
    dy: float,
) -> dict[str, float]:
    width = bbox["x2"] - bbox["x1"]
    height = bbox["y2"] - bbox["y1"]
    x1 = min(max(0.0, bbox["x1"] + dx), image_width - width)
    y1 = min(max(0.0, bbox["y1"] + dy), image_height - height)
    return {
        "x1": round(x1, 6),
        "y1": round(y1, 6),
        "x2": round(x1 + width, 6),
        "y2": round(y1 + height, 6),
    }


def _misaligned_bbox(bbox: dict[str, float], *, image_width: int, image_height: int) -> tuple[dict[str, float], float]:
    width = bbox["x2"] - bbox["x1"]
    height = bbox["y2"] - bbox["y1"]
    candidates: list[tuple[float, dict[str, float]]] = []
    directions = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0), (1.0, 0.25), (-1.0, 0.25))
    for factor in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8):
        for x_direction, y_direction in directions:
            candidate = _translated_bbox(
                bbox,
                image_width=image_width,
                image_height=image_height,
                dx=x_direction * factor * width,
                dy=y_direction * factor * height,
            )
            candidate_iou = _iou(bbox, candidate)
            if 0.2 <= candidate_iou < 0.7:
                candidates.append((candidate_iou, candidate))
    if not candidates:
        raise ValueError(f"Could not create a bbox with IoU in [0.2, 0.7) from {bbox}")
    candidate_iou, candidate = min(candidates, key=lambda item: abs(item[0] - 0.36))
    return candidate, candidate_iou


def _duplicate_bbox(bbox: dict[str, float], *, image_width: int, image_height: int) -> tuple[dict[str, float], float]:
    width = bbox["x2"] - bbox["x1"]
    height = bbox["y2"] - bbox["y1"]
    candidates = [
        _translated_bbox(
            bbox,
            image_width=image_width,
            image_height=image_height,
            dx=x_direction * max(1.0, width * 0.02),
            dy=y_direction * max(0.5, height * 0.01),
        )
        for x_direction, y_direction in ((1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0))
    ]
    distinct_candidates = [(candidate, _iou(bbox, candidate)) for candidate in candidates if candidate != bbox]
    valid_candidates = [(candidate, value) for candidate, value in distinct_candidates if value >= 0.8]
    if not valid_candidates:
        raise ValueError(f"Could not create a duplicate bbox with IoU >= 0.8 from {bbox}")
    return max(valid_candidates, key=lambda item: item[1])


def _size_tag(label: dict[str, Any], *, image_width: int, image_height: int) -> str:
    bbox = _bbox(label)
    area_ratio = ((bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"])) / (image_width * image_height)
    if area_ratio < 0.005:
        return "small_object"
    if area_ratio < 0.03:
        return "medium_object"
    return "large_object"


def _find_label(labels: list[dict[str, Any]], label_id: str, *, context: str) -> dict[str, Any]:
    matches = [label for label in labels if label.get("label_id") == label_id]
    if len(matches) != 1:
        raise ValueError(f"{context}: expected one label {label_id!r}, found {len(matches)}")
    return matches[0]


def _source_copy(gold: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    source = copy.deepcopy(gold)
    image_id = str(gold["image_id"])
    gold_to_source: dict[str, str] = {}
    labels = source.get("labels")
    if not isinstance(labels, list):
        raise ValueError(f"Gold annotation {image_id} has no labels list")
    for index, label in enumerate(labels, start=1):
        gold_label_id = str(label["label_id"])
        source_label_id = f"source-{image_id}-{index:03d}"
        gold_to_source[gold_label_id] = source_label_id
        label["label_id"] = source_label_id
    return source, gold_to_source


def _validate_extra_bbox(bbox: dict[str, float], *, image_width: int, image_height: int) -> None:
    if not (0.0 <= bbox["x1"] < bbox["x2"] <= image_width and 0.0 <= bbox["y1"] < bbox["y2"] <= image_height):
        raise ValueError(f"Extra bbox is outside the image or has no area: {bbox}")


def _build_sample(
    *,
    dataset_root: Path,
    plan_version: str,
    issue_type: str,
    spec: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    image_id = str(spec["image_id"])
    gold_path = dataset_root / "gold_annotations" / f"{image_id}.json"
    image_path = dataset_root / "images" / f"{image_id}.png"
    if not gold_path.is_file() or not image_path.is_file():
        raise FileNotFoundError(f"Missing gold annotation or image for {image_id}")
    gold = _load_object(gold_path)
    source, gold_to_source = _source_copy(gold)
    gold_labels = gold["labels"]
    source_labels = source["labels"]
    image_width = int(gold["image_width"])
    image_height = int(gold["image_height"])
    target_gold: dict[str, Any] | None = None
    target_source: dict[str, Any] | None = None
    issue: dict[str, Any] | None = None

    target_gold_id = spec.get("target_gold_label_id")
    if isinstance(target_gold_id, str):
        target_gold = _find_label(gold_labels, target_gold_id, context=image_id)
        target_source = _find_label(source_labels, gold_to_source[target_gold_id], context=image_id)

    if issue_type == "wrong_class":
        assert target_gold is not None and target_source is not None
        replacement_class = str(spec["replacement_class"])
        gold_class = str(target_gold["class_name"])
        if replacement_class == gold_class:
            raise ValueError(f"{image_id}: wrong_class replacement must differ from gold")
        target_source["class_name"] = replacement_class
        issue = {
            "source_label_id": target_source["label_id"],
            "gold_label_id": target_gold["label_id"],
            "source_class": replacement_class,
            "gold_class": gold_class,
            "source_gold_iou": 1.0,
        }
    elif issue_type == "missing_label":
        assert target_gold is not None and target_source is not None
        source_labels.remove(target_source)
        issue = {
            "source_label_id": None,
            "gold_label_id": target_gold["label_id"],
            "gold_class": target_gold["class_name"],
        }
    elif issue_type == "extra_or_wrong_label":
        extra_bbox = {key: float(spec["extra_bbox"][key]) for key in ("x1", "y1", "x2", "y2")}
        _validate_extra_bbox(extra_bbox, image_width=image_width, image_height=image_height)
        max_gold_iou = max((_iou(extra_bbox, _bbox(label)) for label in gold_labels), default=0.0)
        if max_gold_iou >= 0.05:
            raise ValueError(f"{image_id}: extra bbox overlaps gold labels too much ({max_gold_iou:.4f})")
        extra_label = {
            "label_id": f"source-{image_id}-extra-001",
            "class_name": str(spec["extra_class"]),
            "bbox": extra_bbox,
            "attributes": {"occluded": None, "truncated": None},
        }
        source_labels.append(extra_label)
        target_source = extra_label
        issue = {
            "source_label_id": extra_label["label_id"],
            "gold_label_id": None,
            "source_class": extra_label["class_name"],
            "max_gold_iou": round(max_gold_iou, 6),
        }
    elif issue_type == "bbox_misaligned":
        assert target_gold is not None and target_source is not None
        changed_bbox, source_gold_iou = _misaligned_bbox(
            _bbox(target_gold), image_width=image_width, image_height=image_height
        )
        target_source["bbox"] = changed_bbox
        issue = {
            "source_label_id": target_source["label_id"],
            "gold_label_id": target_gold["label_id"],
            "source_class": target_source["class_name"],
            "gold_class": target_gold["class_name"],
            "source_gold_iou": round(source_gold_iou, 6),
        }
    elif issue_type == "duplicate_label":
        assert target_gold is not None and target_source is not None
        duplicate = copy.deepcopy(target_source)
        duplicate["label_id"] = f"source-{image_id}-duplicate-001"
        duplicate_bbox, duplicate_iou = _duplicate_bbox(
            _bbox(target_gold), image_width=image_width, image_height=image_height
        )
        duplicate["bbox"] = duplicate_bbox
        source_labels.append(duplicate)
        issue = {
            "source_label_id": target_source["label_id"],
            "duplicate_label_id": duplicate["label_id"],
            "gold_label_id": target_gold["label_id"],
            "source_class": target_source["class_name"],
            "duplicate_iou": round(duplicate_iou, 6),
        }
    elif issue_type != "clean_no_issue":
        raise ValueError(f"Unsupported issue type: {issue_type}")

    issue_list: list[dict[str, Any]] = []
    if issue is not None:
        issue.update(
            {
                "issue_id": f"issue-{image_id}-001",
                "issue_type": issue_type,
                "severity": spec["severity"],
                "expected_action": ISSUE_ACTIONS[issue_type],
            }
        )
        issue_list.append(issue)

    size_source = target_gold or target_source
    slice_tags = ["synthetic_source", "pending_human_review", ISSUE_TAGS[issue_type]]
    if size_source is not None:
        slice_tags.append(_size_tag(size_source, image_width=image_width, image_height=image_height))

    sample = {
        "sample_id": f"golden-v0.1-{issue_type}-{image_id}",
        "split": spec["split"],
        "image_path": f"images/{image_id}.png",
        "source_annotation_path": f"source_annotations/{image_id}.json",
        "gold_annotation_path": f"gold_annotations/{image_id}.json",
        "primary_issue_type": issue_type,
        "gold_issues": issue_list,
        "slice_tags": slice_tags,
        "review_status": "pending_human_review",
        "source_generation": {"method": "controlled_synthetic_mutation", "plan_version": plan_version},
        "use_for_metric": False,
    }
    return source, sample


def generate_sources(*, dataset_root: Path, plan_path: Path, manifest_path: Path, overwrite: bool) -> Counter[str]:
    plan = _load_object(plan_path)
    plan_version = str(plan.get("version", "unknown"))
    groups = plan.get("groups")
    if not isinstance(groups, dict):
        raise ValueError(f"{plan_path}: missing groups object")
    if set(groups) != set(ISSUE_ACTIONS):
        raise ValueError(f"{plan_path}: groups must be exactly {sorted(ISSUE_ACTIONS)}")

    generated: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    counts: Counter[str] = Counter()
    planned_ids: list[str] = []
    for issue_type in ISSUE_ACTIONS:
        specs = groups[issue_type]
        if not isinstance(specs, list):
            raise ValueError(f"{plan_path}: {issue_type} must be a list")
        for raw_spec in specs:
            if not isinstance(raw_spec, dict):
                raise ValueError(f"{plan_path}: {issue_type} entries must be objects")
            image_id = str(raw_spec.get("image_id", ""))
            source, sample = _build_sample(
                dataset_root=dataset_root,
                plan_version=plan_version,
                issue_type=issue_type,
                spec=raw_spec,
            )
            generated.append((image_id, source, sample))
            planned_ids.append(image_id)
            counts[issue_type] += 1

    if len(planned_ids) != len(set(planned_ids)):
        duplicates = sorted(image_id for image_id, count in Counter(planned_ids).items() if count > 1)
        raise ValueError(f"Plan uses images more than once: {duplicates}")
    gold_ids = {path.stem for path in (dataset_root / "gold_annotations").glob("*.json")}
    if set(planned_ids) != gold_ids:
        raise ValueError(
            f"Plan/gold mismatch; unplanned={sorted(gold_ids - set(planned_ids))}, "
            f"unknown={sorted(set(planned_ids) - gold_ids)}"
        )

    output_dir = dataset_root / "source_annotations"
    output_paths = [output_dir / f"{image_id}.json" for image_id, _, _ in generated]
    existing_outputs = [path for path in output_paths if path.exists()]
    if existing_outputs and not overwrite:
        raise FileExistsError(f"Source outputs already exist; pass --overwrite: {existing_outputs[0]}")
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8").strip() and not overwrite:
        raise FileExistsError(f"Manifest is not empty; pass --overwrite: {manifest_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    for output_path, (_, source, _) in zip(output_paths, generated, strict=True):
        output_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(
        "".join(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n" for _, _, sample in generated),
        encoding="utf-8",
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate controlled source annotations from gold JSON files.")
    parser.add_argument("--dataset-root", type=Path, default=Path("eval/golden_v0_1"))
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("eval/golden_v0_1/manifests/source_generation_plan.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/golden_v0_1/manifests/samples.jsonl"),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    counts = generate_sources(
        dataset_root=args.dataset_root.resolve(),
        plan_path=args.plan.resolve(),
        manifest_path=args.manifest.resolve(),
        overwrite=args.overwrite,
    )
    print(f"Generated {sum(counts.values())} pending-review source annotations")
    for issue_type in ISSUE_ACTIONS:
        print(f"- {issue_type}: {counts[issue_type]}")
    print("All samples have review_status=pending_human_review and use_for_metric=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
