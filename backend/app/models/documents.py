"""Document registrar + номенклатура дел (ТЗ 3.10)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocTypeConfig(Base):
    """Per-app numbering rules for one document type (ТЗ 3.10.1: маска
    поддерживает префикс/суффикс, год, месяц, порядковый номер, код
    подразделения). Lazily created with defaults, same pattern as
    identity.password_policy/session_policy/file_policy."""

    __tablename__ = "doc_type_config"
    __table_args__ = (
        UniqueConstraint("app_id", "doc_type", name="uq_doc_type_config_app_type"),
        {"schema": "data"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # incoming | outgoing | internal
    prefix: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    suffix: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    include_department: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seq_padding: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    # never | yearly | monthly — controls both the counter reset cadence and
    # whether the formatted number includes a year/month segment at all.
    reset_period: Mapped[str] = mapped_column(String(16), nullable=False, default="yearly")


class RegistrationCounter(Base):
    """Atomic per-(app, doc_type, department, year, month) counter. Rows are
    created on demand via INSERT ... ON CONFLICT — see RegistrarService."""

    __tablename__ = "registration_counter"
    __table_args__ = {"schema": "data"}

    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(32), primary_key=True, default="")
    year: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    month: Mapped[int] = mapped_column(Integer, primary_key=True, default=0)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class DocumentRegistration(Base):
    """One row per registered document — links an arbitrary entity record to
    its assigned registration number (ТЗ 3.10.1)."""

    __tablename__ = "document_registration"
    __table_args__ = (
        UniqueConstraint(
            "app_id", "doc_type", "registration_no", name="uq_document_registration_no"
        ),
        {"schema": "data"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    department_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    registration_no: Mapped[str] = mapped_column(String(128), nullable=False)
    filing_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data.filing_case.id", ondelete="SET NULL"), nullable=True
    )
    registered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FilingCase(Base):
    """Номенклатура дел (ТЗ 3.10.2) — a hierarchical filing classifier."""

    __tablename__ = "filing_case"
    __table_args__ = (
        UniqueConstraint("app_id", "index_code", name="uq_filing_case_app_index"),
        {"schema": "data"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data.filing_case.id", ondelete="RESTRICT"), nullable=True
    )
    index_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    retention_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # open | closed | archived
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # Explicit planned closure date the admin sets — simpler and more
    # predictable than inferring a close date from retention_years alone.
    close_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
