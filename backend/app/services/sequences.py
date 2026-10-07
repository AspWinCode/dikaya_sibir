"""SequenceService: atomic auto-number generation for document registrar fields."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data import Sequence

logger = structlog.get_logger(__name__)


class SequenceNotFoundError(Exception):
    pass


class SequenceAlreadyExistsError(Exception):
    pass


class SequenceService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_sequences(self, app_id: uuid.UUID, entity_id: uuid.UUID) -> list[Sequence]:
        result = await self._db.execute(
            select(Sequence).where(Sequence.app_id == app_id, Sequence.entity_id == entity_id)
        )
        return list(result.scalars())

    async def get_sequence(
        self, app_id: uuid.UUID, entity_id: uuid.UUID, sequence_id: uuid.UUID
    ) -> Sequence:
        result = await self._db.execute(
            select(Sequence).where(
                Sequence.id == sequence_id,
                Sequence.app_id == app_id,
                Sequence.entity_id == entity_id,
            )
        )
        seq = result.scalar_one_or_none()
        if seq is None:
            raise SequenceNotFoundError(str(sequence_id))
        return seq

    async def get_sequence_by_field(self, entity_id: uuid.UUID, field_name: str) -> Sequence | None:
        result = await self._db.execute(
            select(Sequence).where(
                Sequence.entity_id == entity_id,
                Sequence.field_name == field_name,
            )
        )
        return result.scalar_one_or_none()

    async def create_sequence(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_name: str,
        prefix: str = "",
        suffix: str = "",
        padding: int = 0,
        step: int = 1,
        start: int = 1,
        reset_on: str | None = None,
    ) -> Sequence:
        existing = await self.get_sequence_by_field(entity_id, field_name)
        if existing:
            raise SequenceAlreadyExistsError(
                f"Sequence for field '{field_name}' already exists on entity {entity_id}"
            )
        seq = Sequence(
            app_id=app_id,
            entity_id=entity_id,
            field_name=field_name,
            prefix=prefix,
            suffix=suffix,
            padding=padding,
            step=step,
            next_value=start,
            reset_on=reset_on,
        )
        self._db.add(seq)
        await self._db.flush()
        logger.info("sequence_created", entity_id=str(entity_id), field_name=field_name)
        return seq

    async def update_sequence(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        sequence_id: uuid.UUID,
        *,
        prefix: str | None = None,
        suffix: str | None = None,
        padding: int | None = None,
        step: int | None = None,
        reset_on: str | None = None,
    ) -> Sequence:
        seq = await self.get_sequence(app_id, entity_id, sequence_id)
        if prefix is not None:
            seq.prefix = prefix
        if suffix is not None:
            seq.suffix = suffix
        if padding is not None:
            seq.padding = padding
        if step is not None:
            seq.step = step
        if reset_on is not None:
            seq.reset_on = reset_on
        await self._db.flush()
        return seq

    async def delete_sequence(
        self, app_id: uuid.UUID, entity_id: uuid.UUID, sequence_id: uuid.UUID
    ) -> None:
        seq = await self.get_sequence(app_id, entity_id, sequence_id)
        await self._db.delete(seq)
        await self._db.flush()

    async def next_value(self, entity_id: uuid.UUID, field_name: str) -> str:
        """
        Atomically increment and return the formatted next value.

        Uses a conditional UPDATE + RETURNING to ensure no two concurrent
        calls produce the same number even under high concurrency.
        """
        result = await self._db.execute(
            update(Sequence)
            .where(
                Sequence.entity_id == entity_id,
                Sequence.field_name == field_name,
            )
            .values(next_value=Sequence.next_value + Sequence.step)
            .returning(
                Sequence.next_value - Sequence.step,  # value before increment
                Sequence.prefix,
                Sequence.suffix,
                Sequence.padding,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise SequenceNotFoundError(f"No sequence for entity={entity_id} field={field_name}")
        value, prefix, suffix, padding = row
        numeric = str(value).zfill(padding) if padding > 0 else str(value)
        return f"{prefix}{numeric}{suffix}"

    async def fill_autonumber_fields(
        self, entity_id: uuid.UUID, payload: dict, fields: list
    ) -> dict:
        """
        For every field with field_type='autonumber' that is NOT in the payload,
        generate the next sequence value and inject it.
        """
        autonumber_fields = [
            f for f in fields if f.field_type == "autonumber" and f.name not in payload
        ]
        if not autonumber_fields:
            return payload

        result = dict(payload)
        for f in autonumber_fields:
            try:
                result[f.name] = await self.next_value(entity_id, f.name)
            except SequenceNotFoundError:
                logger.warning(
                    "autonumber_sequence_missing",
                    entity_id=str(entity_id),
                    field_name=f.name,
                )
        return result
