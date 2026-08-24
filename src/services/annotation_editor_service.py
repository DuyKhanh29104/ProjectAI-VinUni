"""Versioned persistence for the built-in 2D annotation editor."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from math import isfinite
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.geometry import iou
from src.models.annotation_revision import AnnotationRevision
from src.models.audit_log import AuditLog
from src.models.qa_case import QaCase
from src.models.real_dataset_schemas import (
    AnnotationDocument,
    AnnotationRevisionList,
    AnnotationRevisionSummary,
    RealDatasetImage,
    RealDatasetLabel,
)
from src.services.yolo import canonical_detection_class


class AnnotationConflictError(ValueError):
    """Raised when the editor tries to save an outdated revision."""


class AnnotationEditorService:
    @staticmethod
    async def latest_revision(
        session: AsyncSession,
        *,
        dataset_id: str,
        dataset_version: str,
        split: str,
        image_id: str,
    ) -> AnnotationRevision | None:
        return cast(
            AnnotationRevision | None,
            await session.scalar(
                select(AnnotationRevision)
                .where(
                    AnnotationRevision.dataset_id == dataset_id,
                    AnnotationRevision.dataset_version == dataset_version,
                    AnnotationRevision.split == split,
                    AnnotationRevision.image_id == image_id,
                )
                .order_by(AnnotationRevision.version.desc())
                .limit(1)
            ),
        )

    @staticmethod
    async def latest_for_images(
        session: AsyncSession,
        *,
        dataset_id: str,
        dataset_version: str,
        split: str,
        image_ids: list[str],
    ) -> dict[str, AnnotationRevision]:
        if not image_ids:
            return {}
        revisions = (
            await session.scalars(
                select(AnnotationRevision)
                .where(
                    AnnotationRevision.dataset_id == dataset_id,
                    AnnotationRevision.dataset_version == dataset_version,
                    AnnotationRevision.split == split,
                    AnnotationRevision.image_id.in_(image_ids),
                )
                .order_by(AnnotationRevision.image_id, AnnotationRevision.version.desc())
            )
        ).all()
        latest: dict[str, AnnotationRevision] = {}
        for revision in revisions:
            latest.setdefault(revision.image_id, revision)
        return latest

    @classmethod
    async def document(
        cls,
        session: AsyncSession,
        *,
        image: RealDatasetImage,
        dataset_id: str,
        dataset_version: str,
    ) -> AnnotationDocument:
        revision = await cls.latest_revision(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
        )
        return cls.to_document(image, dataset_id, dataset_version, revision)

    @staticmethod
    def to_document(
        image: RealDatasetImage,
        dataset_id: str,
        dataset_version: str,
        revision: AnnotationRevision | None,
    ) -> AnnotationDocument:
        if revision is None:
            labels = image.labels
            original = image.labels
            version = 0
        else:
            labels = [RealDatasetLabel.model_validate(item) for item in revision.labels_json]
            original = [RealDatasetLabel.model_validate(item) for item in revision.original_labels_json]
            version = revision.version
        effective_image = image.model_copy(update={"labels": labels, "label_count": len(labels)})
        return AnnotationDocument(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
            revision=version,
            image=effective_image,
            labels=labels,
            original_labels=original,
            updated_at=revision.created_at if revision else None,
            updated_by=revision.actor_id if revision else None,
            change_note=revision.change_note if revision else None,
        )

    @classmethod
    async def save(
        cls,
        session: AsyncSession,
        *,
        image: RealDatasetImage,
        dataset_id: str,
        dataset_version: str,
        expected_revision: int,
        labels: list[RealDatasetLabel],
        actor_id: str | None,
        change_note: str | None,
    ) -> AnnotationDocument:
        cls._validate_labels(image, labels)
        latest = await cls.latest_revision(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
        )
        current_version = latest.version if latest else 0
        if current_version != expected_revision:
            raise AnnotationConflictError(
                f"Annotation revision changed from {expected_revision} to {current_version}; reload before saving."
            )

        now = datetime.now(UTC)
        previous_labels = (
            deepcopy(latest.labels_json)
            if latest
            else [item.model_dump(mode="json", by_alias=True) for item in image.labels]
        )
        revision = AnnotationRevision(
            id=str(uuid4()),
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
            version=current_version + 1,
            labels_json=[item.model_dump(mode="json", by_alias=True) for item in labels],
            original_labels_json=(
                deepcopy(latest.original_labels_json)
                if latest
                else [item.model_dump(mode="json", by_alias=True) for item in image.labels]
            ),
            actor_id=actor_id,
            change_note=change_note.strip() if change_note and change_note.strip() else None,
            created_at=now,
        )
        session.add(revision)
        await cls._update_qa_cases(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
            revision=revision,
            previous_labels=previous_labels,
            actor_id=actor_id,
            timestamp=now,
        )
        try:
            await session.commit()
        except IntegrityError as error:
            await session.rollback()
            raise AnnotationConflictError("Another editor saved this image first; reload before saving.") from error
        return cls.to_document(image, dataset_id, dataset_version, revision)

    @classmethod
    async def restore(
        cls,
        session: AsyncSession,
        *,
        image: RealDatasetImage,
        dataset_id: str,
        dataset_version: str,
        expected_revision: int,
        target_revision: int,
        actor_id: str | None,
        change_note: str | None,
    ) -> AnnotationDocument:
        latest = await cls.latest_revision(
            session,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            split=image.split,
            image_id=image.id,
        )
        current_version = latest.version if latest else 0
        if current_version != expected_revision:
            raise AnnotationConflictError(
                f"Annotation revision changed from {expected_revision} to {current_version}; reload before restoring."
            )
        if target_revision == 0:
            labels = (
                [RealDatasetLabel.model_validate(item) for item in latest.original_labels_json]
                if latest
                else image.labels
            )
        else:
            target = await session.scalar(
                select(AnnotationRevision).where(
                    AnnotationRevision.dataset_id == dataset_id,
                    AnnotationRevision.dataset_version == dataset_version,
                    AnnotationRevision.split == image.split,
                    AnnotationRevision.image_id == image.id,
                    AnnotationRevision.version == target_revision,
                )
            )
            if target is None:
                raise FileNotFoundError(f"Annotation revision {target_revision} does not exist.")
            labels = [RealDatasetLabel.model_validate(item) for item in target.labels_json]
        note = change_note or f"Restored annotation revision {target_revision}"
        return await cls.save(
            session,
            image=image,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            expected_revision=expected_revision,
            labels=labels,
            actor_id=actor_id,
            change_note=note,
        )

    @staticmethod
    async def history(
        session: AsyncSession,
        *,
        dataset_id: str,
        dataset_version: str,
        split: str,
        image_id: str,
    ) -> AnnotationRevisionList:
        revisions = (
            await session.scalars(
                select(AnnotationRevision)
                .where(
                    AnnotationRevision.dataset_id == dataset_id,
                    AnnotationRevision.dataset_version == dataset_version,
                    AnnotationRevision.split == split,
                    AnnotationRevision.image_id == image_id,
                )
                .order_by(AnnotationRevision.version.desc())
            )
        ).all()
        results = [
            AnnotationRevisionSummary(
                revision=item.version,
                label_count=len(item.labels_json),
                actor_id=item.actor_id,
                change_note=item.change_note,
                created_at=item.created_at,
            )
            for item in revisions
        ]
        return AnnotationRevisionList(count=len(results), results=results)

    @staticmethod
    def _validate_labels(_image: RealDatasetImage, labels: list[RealDatasetLabel]) -> None:
        ids = [item.id for item in labels]
        if len(ids) != len(set(ids)):
            raise ValueError("Annotation IDs must be unique within one image.")
        for label in labels:
            if not label.class_name.strip():
                raise ValueError("Annotation class name cannot be empty.")
            box = label.bbox
            if not all(isfinite(value) for value in (box.x1, box.y1, box.x2, box.y2)):
                raise ValueError(f"Annotation {label.id} has non-finite coordinates.")

    @staticmethod
    def _changed_label_ids(
        previous_labels: list[dict[str, Any]],
        next_labels: list[dict[str, Any]],
    ) -> tuple[set[str], set[str]]:
        previous = {str(item.get("id")): item for item in previous_labels if item.get("id") is not None}
        current = {str(item.get("id")): item for item in next_labels if item.get("id") is not None}
        changed = {
            label_id
            for label_id in previous.keys() | current.keys()
            if previous.get(label_id) != current.get(label_id)
        }
        return changed, current.keys() - previous.keys()

    @staticmethod
    def _missing_case_matches_added_label(
        evidence: dict[str, Any],
        added_labels: list[dict[str, Any]],
    ) -> bool:
        issue_evidence = evidence.get("issueEvidence")
        if not isinstance(issue_evidence, dict):
            return False
        prediction_bbox = issue_evidence.get("bbox")
        raw_prediction_class = str(issue_evidence.get("class_name") or "").strip()
        prediction_class = canonical_detection_class(raw_prediction_class) or raw_prediction_class.lower()
        if not isinstance(prediction_bbox, dict) or not prediction_class:
            return False
        for label in added_labels:
            label_bbox = label.get("bbox")
            raw_label_class = str(label.get("className") or label.get("class_name") or "").strip()
            label_class = canonical_detection_class(raw_label_class) or raw_label_class.lower()
            if label_class != prediction_class or not isinstance(label_bbox, dict):
                continue
            if iou(label_bbox, prediction_bbox) >= 0.1:
                return True
        return False

    @staticmethod
    async def _update_qa_cases(
        session: AsyncSession,
        *,
        dataset_id: str,
        dataset_version: str,
        split: str,
        image_id: str,
        revision: AnnotationRevision,
        previous_labels: list[dict[str, Any]],
        actor_id: str | None,
        timestamp: datetime,
    ) -> None:
        cases = (
            await session.scalars(
                select(QaCase).where(
                    QaCase.dataset_id == dataset_id,
                    QaCase.dataset_version == dataset_version,
                    QaCase.source_split == split,
                    QaCase.source_image_id == image_id,
                )
            )
        ).all()
        changed_ids, added_ids = AnnotationEditorService._changed_label_ids(
            previous_labels,
            revision.labels_json,
        )
        added_labels = [item for item in revision.labels_json if str(item.get("id")) in added_ids]
        for qa_case in cases:
            evidence = deepcopy(qa_case.evidence_json or {})
            evidence.setdefault("originalGroundTruthLabels", deepcopy(evidence.get("groundTruthLabels", [])))
            evidence["groundTruthLabels"] = deepcopy(revision.labels_json)
            evidence["annotationRevision"] = revision.version
            qa_case.evidence_json = evidence

            issue_evidence = evidence.get("issueEvidence")
            issue_evidence = issue_evidence if isinstance(issue_evidence, dict) else {}
            related_ids = {
                value
                for value in (
                    qa_case.target_track_id,
                    issue_evidence.get("gt_id"),
                    issue_evidence.get("label_a"),
                    issue_evidence.get("label_b"),
                )
                if isinstance(value, str)
            }
            affected = bool(related_ids.intersection(changed_ids))
            if qa_case.error_type == "missing_object" and qa_case.target_track_id is None:
                affected = AnnotationEditorService._missing_case_matches_added_label(evidence, added_labels)
            if not affected:
                continue

            before_status = qa_case.status
            qa_case.status = "corrected"
            qa_case.updated_at = timestamp
            session.add(
                AuditLog(
                    id=str(uuid4()),
                    case_id=qa_case.id,
                    event_type="annotation_revision_saved",
                    actor_type="user",
                    actor_id=actor_id,
                    before_json={"status": before_status, "revision": revision.version - 1},
                    after_json={
                        "status": "corrected",
                        "revision": revision.version,
                        "labelCount": len(revision.labels_json),
                    },
                    metadata_json={"source": "built_in_editor", "split": split, "imageId": image_id},
                    created_at=timestamp,
                )
            )
