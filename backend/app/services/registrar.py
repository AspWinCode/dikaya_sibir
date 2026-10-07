"""RegistrarService: document numbering + номенклатура дел (ТЗ 3.10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import (
    DocTypeConfig,
    DocumentRegistration,
    FilingCase,
    RegistrationCounter,
)
from app.schemas.documents import (
    DOC_TYPES,
    DocTypeConfigUpdate,
    FilingCaseCreate,
    FilingCaseUpdate,
)


class DocTypeNotFoundError(Exception):
    pass


class RegistrationConflictError(Exception):
    """Raised if the atomically-generated number somehow collides — should
    only happen if a row was hand-inserted outside this service."""

    pass


class FilingCaseNotFoundError(Exception):
    """Also raised for a parent_id that doesn't exist in this app — case
    hierarchy can only be built by attaching a new case under an existing
    one, so a cycle can never be introduced."""

    pass


_DEFAULTS = {
    "incoming": {"prefix": "ВХ-"},
    "outgoing": {"prefix": "ИСХ-"},
    "internal": {"prefix": "ВН-"},
}


class RegistrarService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Doc type configuration
    # ------------------------------------------------------------------

    async def get_doc_type_config(self, app_id: uuid.UUID, doc_type: str) -> DocTypeConfig:
        result = await self._db.execute(
            select(DocTypeConfig).where(
                DocTypeConfig.app_id == app_id, DocTypeConfig.doc_type == doc_type
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = DocTypeConfig(
                app_id=app_id,
                doc_type=doc_type,
                prefix=_DEFAULTS.get(doc_type, {}).get("prefix", ""),
            )
            self._db.add(config)
            await self._db.flush()
        return config

    async def list_doc_type_configs(self, app_id: uuid.UUID) -> list[DocTypeConfig]:
        return [await self.get_doc_type_config(app_id, dt) for dt in DOC_TYPES]

    async def update_doc_type_config(
        self,
        app_id: uuid.UUID,
        doc_type: str,
        data: DocTypeConfigUpdate,
    ) -> DocTypeConfig:
        config = await self.get_doc_type_config(app_id, doc_type)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(config, field, value)
        await self._db.flush()
        return config

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_document(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        doc_type: str,
        department_code: str | None = None,
        filing_case_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> DocumentRegistration:
        config = await self.get_doc_type_config(app_id, doc_type)
        now = now or datetime.now(UTC)

        dept = (department_code or "") if config.include_department else ""
        year = 0 if config.reset_period == "never" else now.year
        month = now.month if config.reset_period == "monthly" else 0

        seq = await self._next_counter_value(app_id, doc_type, dept, year, month)
        registration_no = _format_registration_no(config, dept, year, month, seq)

        reg = DocumentRegistration(
            app_id=app_id,
            entity_id=entity_id,
            record_id=record_id,
            doc_type=doc_type,
            department_code=department_code,
            registration_no=registration_no,
            filing_case_id=filing_case_id,
            registered_by=actor_id,
        )
        self._db.add(reg)
        try:
            await self._db.flush()
        except IntegrityError as exc:
            # The counter is atomic, so this should only happen if a number
            # was hand-inserted (e.g. a data migration) outside this service.
            raise RegistrationConflictError(registration_no) from exc
        return reg

    async def _next_counter_value(
        self,
        app_id: uuid.UUID,
        doc_type: str,
        department_code: str,
        year: int,
        month: int,
    ) -> int:
        """Atomically create-or-increment the counter row and return the
        value to use for THIS document (the value before incrementing)."""
        insert_stmt = pg_insert(RegistrationCounter).values(
            app_id=app_id,
            doc_type=doc_type,
            department_code=department_code,
            year=year,
            month=month,
            next_value=2,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["app_id", "doc_type", "department_code", "year", "month"],
            set_={"next_value": RegistrationCounter.next_value + 1},
        ).returning(RegistrationCounter.next_value)
        result = await self._db.execute(upsert_stmt)
        new_value: int = result.scalar_one()
        return new_value - 1

    async def list_registrations(
        self,
        app_id: uuid.UUID,
        doc_type: str | None = None,
        filing_case_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[DocumentRegistration]:
        stmt = (
            select(DocumentRegistration)
            .where(DocumentRegistration.app_id == app_id)
            .order_by(DocumentRegistration.registered_at.desc())
            .limit(limit)
        )
        if doc_type:
            stmt = stmt.where(DocumentRegistration.doc_type == doc_type)
        if filing_case_id:
            stmt = stmt.where(DocumentRegistration.filing_case_id == filing_case_id)
        return list((await self._db.execute(stmt)).scalars())

    # ------------------------------------------------------------------
    # Filing cases (номенклатура дел)
    # ------------------------------------------------------------------

    async def list_filing_cases(self, app_id: uuid.UUID) -> list[FilingCase]:
        result = await self._db.execute(
            select(FilingCase).where(FilingCase.app_id == app_id).order_by(FilingCase.index_code)
        )
        return list(result.scalars())

    async def create_filing_case(self, app_id: uuid.UUID, data: FilingCaseCreate) -> FilingCase:
        if data.parent_id is not None:
            await self._fetch_case(app_id, data.parent_id)  # 404s if missing/foreign
        case = FilingCase(
            app_id=app_id,
            parent_id=data.parent_id,
            index_code=data.index_code,
            title=data.title,
            retention_years=data.retention_years,
            storage_location=data.storage_location,
            close_by=data.close_by,
            responsible_user_id=data.responsible_user_id,
        )
        self._db.add(case)
        await self._db.flush()
        return case

    async def update_filing_case(
        self,
        app_id: uuid.UUID,
        case_id: uuid.UUID,
        data: FilingCaseUpdate,
    ) -> FilingCase:
        case = await self._fetch_case(app_id, case_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(case, field, value)
        if data.status == "closed" and case.closed_at is None:
            case.closed_at = datetime.now(UTC)
        await self._db.flush()
        return case

    async def delete_filing_case(self, app_id: uuid.UUID, case_id: uuid.UUID) -> None:
        case = await self._fetch_case(app_id, case_id)
        await self._db.delete(case)
        await self._db.flush()

    async def _fetch_case(self, app_id: uuid.UUID, case_id: uuid.UUID) -> FilingCase:
        result = await self._db.execute(
            select(FilingCase).where(FilingCase.id == case_id, FilingCase.app_id == app_id)
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise FilingCaseNotFoundError(str(case_id))
        return case

    async def close_overdue_cases(self, now: datetime | None = None) -> list[FilingCase]:
        """Auto-close every open case past its close_by date (ТЗ 3.10.2).
        Returns the cases that were closed, so the caller can notify their
        responsible_user_id."""
        now = now or datetime.now(UTC)
        result = await self._db.execute(
            select(FilingCase).where(FilingCase.status == "open", FilingCase.close_by <= now.date())
        )
        cases = list(result.scalars())
        for case in cases:
            case.status = "closed"
            case.closed_at = now
        await self._db.flush()
        return cases


def _format_registration_no(
    config: DocTypeConfig, dept: str, year: int, month: int, seq: int
) -> str:
    """ВХ-2026/04-0001 style: prefix[+dept-][year[/month]]-seq[suffix].
    Matches ТЗ 3.10.1's example exactly for the default (yearly, no dept)
    config; department and month segments are added only when configured."""
    parts = [config.prefix]
    if dept:
        parts.append(f"{dept}-")
    if config.reset_period != "never":
        parts.append(str(year))
        if config.reset_period == "monthly":
            parts.append(f"/{month:02d}")
        parts.append("-")
    parts.append(str(seq).zfill(config.seq_padding))
    parts.append(config.suffix)
    return "".join(parts)
