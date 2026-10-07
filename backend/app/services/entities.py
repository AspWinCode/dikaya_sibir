import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.metamodel import Entity, Field, Relation
from app.schemas.entities import (
    EntityCreate,
    EntityRead,
    EntityUpdate,
    FieldCreate,
    FieldRead,
    FieldReorderRequest,
    FieldUpdate,
    RelationCreate,
    RelationRead,
    RelationUpdate,
)

logger = structlog.get_logger(__name__)


def _reverse_relation_type(relation_type: str) -> str:
    return {
        "one_to_one": "one_to_one",
        "one_to_many": "many_to_one",
        "many_to_many": "many_to_many",
    }.get(relation_type, relation_type)


class EntityNotFoundError(Exception):
    pass


class FieldNotFoundError(Exception):
    pass


class EntityConflictError(Exception):
    pass


class FieldConflictError(Exception):
    pass


class RelationConflictError(Exception):
    pass


class EntityService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------
    async def list_entities(self, app_id: uuid.UUID) -> list[EntityRead]:
        result = await self._db.execute(
            select(Entity)
            .where(Entity.app_id == app_id)
            .options(selectinload(Entity.fields))
            .order_by(Entity.display_name.asc())
        )
        return [EntityRead.model_validate(e) for e in result.scalars()]

    async def get_entity(self, app_id: uuid.UUID, entity_id: uuid.UUID) -> EntityRead:
        entity = await self._fetch_entity(app_id, entity_id)
        return EntityRead.model_validate(entity)

    async def create_entity(self, app_id: uuid.UUID, data: EntityCreate) -> EntityRead:
        existing = await self._db.execute(
            select(Entity).where(Entity.app_id == app_id, Entity.slug == data.slug)
        )
        if existing.scalar_one_or_none():
            raise EntityConflictError(f"Entity slug already exists: {data.slug}")

        entity = Entity(
            app_id=app_id,
            slug=data.slug,
            display_name=data.display_name,
            name_plural=data.name_plural,
            description=data.description,
            icon=data.icon,
            color=data.color,
            settings=data.settings,
        )
        self._db.add(entity)
        await self._db.flush()

        # Create system fields: id, created_at, updated_at, author, is_deleted
        system_fields = [
            Field(
                entity_id=entity.id,
                app_id=app_id,
                name="id",
                display_name="ID",
                field_type="text",
                is_system=True,
                is_required=True,
                is_unique=True,
                display_order=0,
            ),
            Field(
                entity_id=entity.id,
                app_id=app_id,
                name="created_at",
                display_name="Дата создания",
                field_type="datetime",
                is_system=True,
                is_required=True,
                display_order=1,
            ),
            Field(
                entity_id=entity.id,
                app_id=app_id,
                name="updated_at",
                display_name="Дата изменения",
                field_type="datetime",
                is_system=True,
                is_required=True,
                display_order=2,
            ),
            Field(
                entity_id=entity.id,
                app_id=app_id,
                name="author_id",
                display_name="Автор",
                field_type="text",
                is_system=True,
                is_required=False,
                display_order=3,
            ),
            Field(
                entity_id=entity.id,
                app_id=app_id,
                name="is_deleted",
                display_name="Статус удаления",
                field_type="boolean",
                is_system=True,
                is_required=True,
                display_order=4,
            ),
        ]
        for f in system_fields:
            self._db.add(f)

        await self._db.flush()
        entity.field_order = [str(f.id) for f in system_fields]
        await self._db.flush()

        logger.info("entity_created", entity_id=str(entity.id), slug=data.slug, app_id=str(app_id))
        return await self.get_entity(app_id, entity.id)

    async def update_entity(
        self, app_id: uuid.UUID, entity_id: uuid.UUID, data: EntityUpdate
    ) -> EntityRead:
        entity = await self._fetch_entity(app_id, entity_id)
        if entity.is_system:
            raise PermissionError("Cannot modify system entity")

        if data.display_name is not None:
            entity.display_name = data.display_name
        if data.name_plural is not None:
            entity.name_plural = data.name_plural
        if data.description is not None:
            entity.description = data.description
        if data.icon is not None:
            entity.icon = data.icon
        if data.color is not None:
            entity.color = data.color
        if data.settings is not None:
            entity.settings = data.settings

        await self._db.flush()
        return await self.get_entity(app_id, entity_id)

    async def delete_entity(self, app_id: uuid.UUID, entity_id: uuid.UUID) -> None:
        entity = await self._fetch_entity(app_id, entity_id)
        if entity.is_system:
            raise PermissionError("Cannot delete system entity")
        await self._db.delete(entity)
        await self._db.flush()
        logger.info("entity_deleted", entity_id=str(entity_id))

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------
    async def create_field(
        self, app_id: uuid.UUID, entity_id: uuid.UUID, data: FieldCreate
    ) -> FieldRead:
        entity = await self._fetch_entity(app_id, entity_id)
        existing = await self._db.execute(
            select(Field).where(Field.entity_id == entity_id, Field.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise FieldConflictError(f"Field name already exists: {data.name}")

        # Next display order
        max_order_res = await self._db.execute(
            select(Field.display_order)
            .where(Field.entity_id == entity_id)
            .order_by(Field.display_order.desc())
            .limit(1)
        )
        max_order = max_order_res.scalar_one_or_none() or 0

        field = Field(
            entity_id=entity_id,
            app_id=app_id,
            name=data.name,
            display_name=data.display_name,
            field_type=data.field_type.value,
            is_required=data.is_required,
            is_unique=data.is_unique,
            is_indexed=data.is_indexed,
            is_sensitive=data.is_sensitive,
            default_value=data.default_value,
            validation_rules=data.validation_rules,
            field_options=data.field_options,
            formula_definition=data.formula_definition,
            display_order=max_order + 1,
        )
        self._db.add(field)
        await self._db.flush()

        # Append to field_order on entity
        entity.field_order = [*entity.field_order, str(field.id)]
        await self._db.flush()

        logger.info("field_created", field_id=str(field.id), entity_id=str(entity_id))
        return FieldRead.model_validate(field)

    async def update_field(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_id: uuid.UUID,
        data: FieldUpdate,
    ) -> FieldRead:
        field = await self._fetch_field(entity_id, field_id)
        if field.is_system:
            raise PermissionError("Cannot modify system field")

        if data.display_name is not None:
            field.display_name = data.display_name
        if data.is_required is not None:
            field.is_required = data.is_required
        if data.is_unique is not None:
            field.is_unique = data.is_unique
        if data.is_indexed is not None:
            field.is_indexed = data.is_indexed
        if data.default_value is not None:
            field.default_value = data.default_value
        if data.validation_rules is not None:
            field.validation_rules = data.validation_rules
        if data.field_options is not None:
            field.field_options = data.field_options
        if data.formula_definition is not None:
            field.formula_definition = data.formula_definition

        await self._db.flush()
        await self._db.refresh(field, attribute_names=["updated_at"])
        return FieldRead.model_validate(field)

    async def delete_field(
        self, app_id: uuid.UUID, entity_id: uuid.UUID, field_id: uuid.UUID
    ) -> None:
        field = await self._fetch_field(entity_id, field_id)
        if field.is_system:
            raise PermissionError("Cannot delete system field")

        entity = await self._fetch_entity(app_id, entity_id)
        entity.field_order = [fid for fid in entity.field_order if fid != str(field_id)]

        await self._db.delete(field)
        await self._db.flush()

    async def reorder_fields(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        req: FieldReorderRequest,
    ) -> EntityRead:
        entity = await self._fetch_entity(app_id, entity_id)

        # Validate all field ids belong to this entity
        result = await self._db.execute(select(Field.id).where(Field.entity_id == entity_id))
        existing_ids = {str(r) for r in result.scalars()}
        incoming_ids = {str(fid) for fid in req.field_ids}
        if incoming_ids != existing_ids:
            raise ValueError("field_ids must contain all fields of the entity exactly once")

        entity.field_order = [str(fid) for fid in req.field_ids]

        # Update display_order on each field
        for order, fid in enumerate(req.field_ids):
            field = await self._fetch_field(entity_id, fid)
            field.display_order = order

        await self._db.flush()
        return await self.get_entity(app_id, entity_id)

    # ------------------------------------------------------------------
    # Relations
    # ------------------------------------------------------------------
    async def list_relations(self, app_id: uuid.UUID) -> list[RelationRead]:
        result = await self._db.execute(select(Relation).where(Relation.app_id == app_id))
        return [RelationRead.model_validate(r) for r in result.scalars()]

    async def create_relation(self, app_id: uuid.UUID, data: RelationCreate) -> RelationRead:
        # Fetch both entities (validates they belong to this app)
        from_entity = await self._fetch_entity(app_id, data.from_entity_id)
        to_entity = await self._fetch_entity(app_id, data.to_entity_id)

        # Reject self-relations
        if data.from_entity_id == data.to_entity_id:
            raise RelationConflictError("Cannot create a relation from an entity to itself")

        # Reject an exact duplicate — same pair of entities, same type, same
        # from_field_name. Deliberately NOT keyed on just (from, to, type):
        # an entity legitimately needs more than one relation to the same
        # target under different field names (e.g. a transfer record's
        # "откуда"/"куда", both one_to_many to the same Помещение entity) —
        # rejecting those as duplicates was a bug, not a real constraint.
        existing = await self._db.execute(
            select(Relation).where(
                Relation.app_id == app_id,
                Relation.from_entity_id == data.from_entity_id,
                Relation.to_entity_id == data.to_entity_id,
                Relation.relation_type == data.relation_type.value,
                Relation.from_field_name == data.from_field_name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise RelationConflictError(
                f"Relation {data.relation_type.value} via field "
                f"{data.from_field_name!r} between these entities already exists"
            )

        relation = Relation(
            app_id=app_id,
            from_entity_id=data.from_entity_id,
            to_entity_id=data.to_entity_id,
            relation_type=data.relation_type.value,
            from_field_name=data.from_field_name,
            to_field_name=data.to_field_name,
            display_name=data.display_name,
            settings=data.settings,
        )
        self._db.add(relation)
        await self._db.flush()

        # Auto-create relation field on from_entity
        await self._upsert_relation_field(
            entity=from_entity,
            app_id=app_id,
            field_name=data.from_field_name,
            display_name=data.display_name or to_entity.display_name,
            target_entity_id=data.to_entity_id,
            relation_type=data.relation_type.value,
            relation_id=str(relation.id),
        )

        # Auto-create reverse field on to_entity when to_field_name is provided
        # (required for many_to_many, optional for others)
        if data.to_field_name:
            reverse_type = _reverse_relation_type(data.relation_type.value)
            await self._upsert_relation_field(
                entity=to_entity,
                app_id=app_id,
                field_name=data.to_field_name,
                display_name=from_entity.display_name,
                target_entity_id=data.from_entity_id,
                relation_type=reverse_type,
                relation_id=str(relation.id),
            )

        logger.info("relation_created", relation_id=str(relation.id), app_id=str(app_id))
        return RelationRead.model_validate(relation)

    async def update_relation(
        self, app_id: uuid.UUID, relation_id: uuid.UUID, data: RelationUpdate
    ) -> RelationRead:
        result = await self._db.execute(
            select(Relation).where(Relation.id == relation_id, Relation.app_id == app_id)
        )
        relation = result.scalar_one_or_none()
        if relation is None:
            raise EntityNotFoundError(str(relation_id))

        if data.display_name is not None:
            relation.display_name = data.display_name or None

        # Rename auto-created fields when field names change
        for new_name, entity_id in (
            (data.from_field_name, relation.from_entity_id),
            (data.to_field_name, relation.to_entity_id),
        ):
            if new_name is None:
                continue
            fields_result = await self._db.execute(
                select(Field).where(
                    Field.app_id == app_id,
                    Field.entity_id == entity_id,
                    Field.field_type == "relation",
                )
            )
            target_field = next(
                (
                    f
                    for f in fields_result.scalars()
                    if f.field_options.get("relation_id") == str(relation_id)
                ),
                None,
            )
            if target_field is None:
                continue
            if target_field.name == new_name:
                continue
            # Check no other field with new name exists on this entity
            conflict = await self._db.execute(
                select(Field).where(
                    Field.entity_id == entity_id,
                    Field.name == new_name,
                )
            )
            if conflict.scalar_one_or_none() is not None:
                raise FieldConflictError(f"Field '{new_name}' already exists on entity")
            target_field.name = new_name
            # Keep relation row in sync
            if entity_id == relation.from_entity_id:
                relation.from_field_name = new_name
            else:
                relation.to_field_name = new_name

        await self._db.flush()
        logger.info("relation_updated", relation_id=str(relation_id), app_id=str(app_id))
        return RelationRead.model_validate(relation)

    async def delete_relation(self, app_id: uuid.UUID, relation_id: uuid.UUID) -> None:
        result = await self._db.execute(
            select(Relation).where(Relation.id == relation_id, Relation.app_id == app_id)
        )
        relation = result.scalar_one_or_none()
        if relation is None:
            raise EntityNotFoundError(str(relation_id))

        # Remove all relation-type fields that were auto-created for this relation
        fields_result = await self._db.execute(
            select(Field).where(Field.app_id == app_id, Field.field_type == "relation")
        )
        for field in fields_result.scalars():
            if field.field_options.get("relation_id") == str(relation_id):
                entity_result = await self._db.execute(
                    select(Entity)
                    .where(Entity.id == field.entity_id)
                    .options(selectinload(Entity.fields))
                )
                entity = entity_result.scalar_one_or_none()
                if entity:
                    entity.field_order = [fid for fid in entity.field_order if fid != str(field.id)]
                await self._db.delete(field)
        await self._db.flush()
        await self._db.delete(relation)
        await self._db.flush()

    # ------------------------------------------------------------------
    async def _upsert_relation_field(
        self,
        entity: Entity,
        app_id: uuid.UUID,
        field_name: str,
        display_name: str,
        target_entity_id: uuid.UUID,
        relation_type: str,
        relation_id: str,
    ) -> None:
        """Create (or skip if exists) a relation-type field on entity."""
        existing = await self._db.execute(
            select(Field).where(Field.entity_id == entity.id, Field.name == field_name)
        )
        if existing.scalar_one_or_none() is not None:
            return

        max_order_res = await self._db.execute(
            select(Field.display_order)
            .where(Field.entity_id == entity.id)
            .order_by(Field.display_order.desc())
            .limit(1)
        )
        max_order = max_order_res.scalar_one_or_none() or 0

        field = Field(
            entity_id=entity.id,
            app_id=app_id,
            name=field_name,
            display_name=display_name,
            field_type="relation",
            field_options={
                "target_entity_id": str(target_entity_id),
                "relation_type": relation_type,
                "relation_id": relation_id,
            },
            display_order=max_order + 1,
        )
        self._db.add(field)
        await self._db.flush()
        entity.field_order = [*entity.field_order, str(field.id)]
        await self._db.flush()

    # ------------------------------------------------------------------
    async def _fetch_entity(self, app_id: uuid.UUID, entity_id: uuid.UUID) -> Entity:
        result = await self._db.execute(
            select(Entity)
            .where(Entity.id == entity_id, Entity.app_id == app_id)
            .options(selectinload(Entity.fields))
        )
        entity = result.scalar_one_or_none()
        if entity is None:
            raise EntityNotFoundError(str(entity_id))
        return entity

    async def _fetch_field(self, entity_id: uuid.UUID, field_id: uuid.UUID) -> Field:
        result = await self._db.execute(
            select(Field).where(Field.id == field_id, Field.entity_id == entity_id)
        )
        field = result.scalar_one_or_none()
        if field is None:
            raise FieldNotFoundError(str(field_id))
        return field
