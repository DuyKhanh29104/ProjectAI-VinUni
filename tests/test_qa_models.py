from src.db.base import Base
from src.models import AnnotationRevision, AuditLog, QaCase, QaEvaluation


def test_qa_case_and_audit_tables_are_registered() -> None:
    assert QaCase.__tablename__ == "qa_cases"
    assert AuditLog.__tablename__ == "audit_logs"
    assert QaEvaluation.__tablename__ == "qa_evaluations"
    assert AnnotationRevision.__tablename__ == "annotation_revisions"
    assert {"qa_cases", "qa_evaluations", "audit_logs", "annotation_revisions"}.issubset(Base.metadata.tables)


def test_audit_log_references_qa_case() -> None:
    foreign_keys = Base.metadata.tables["audit_logs"].foreign_keys
    assert {foreign_key.target_fullname for foreign_key in foreign_keys} == {"qa_cases.id"}
