import uuid
from datetime import datetime

import sqlalchemy as sa
import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalog import App, AppMember, AppSnapshot
from app.models.identity import User
from app.models.metamodel import Entity, Field, Relation
from app.schemas.apps import (
    AppCloneCreate,
    AppCreate,
    AppMemberAdd,
    AppMemberRead,
    AppRead,
    AppSnapshotCreate,
    AppSnapshotRead,
    AppUpdate,
    PublishCheckResult,
)
from app.schemas.common import CursorPage

logger = structlog.get_logger(__name__)


class AppNotFoundError(Exception):
    pass


class AppConflictError(Exception):
    pass


class AppPermissionError(Exception):
    pass


class AppPublishBlockedError(Exception):
    """Raised when the pre-publish integrity check (ТЗ 3.11.1) finds
    error-severity issues. Carries the full check result so the caller can
    show every issue, not just the fact that publishing was blocked."""

    def __init__(self, issues: list) -> None:
        self.issues = issues
        super().__init__(f"Publication blocked by {len(issues)} integrity issue(s)")


def _encode_cursor(app_id: uuid.UUID, created_at: datetime) -> str:
    import base64

    raw = f"{created_at.isoformat()}|{app_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    import base64

    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, uid = raw.split("|", 1)
    return datetime.fromisoformat(ts), uuid.UUID(uid)


def _slugify(name: str) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    safe = base if len(base) >= 2 else f"app-{base}"
    return f"{safe}-{uuid.uuid4().hex[:6]}"


class AppService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_apps(
        self,
        actor_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
        search: str | None = None,
        include_archived: bool = False,
    ) -> CursorPage[AppRead]:
        # Deliberately no platform_admin/org-wide bypass: holding the
        # platform_admin role, or merely belonging to the same org, manages
        # the platform/org, not an automatic membership in every app in it.
        # An app-level AppMember row (or being the owner) is required to see
        # an app here, same as everyone else — "can view org metadata" and
        # "can open this app's editor/runtime/data" are different questions;
        # an org-wide admin listing, if ever needed, belongs in its own
        # endpoint rather than silently widening this one.
        stmt = select(App).order_by(App.created_at.asc(), App.id.asc())
        stmt = stmt.where(
            or_(
                App.owner_id == actor_id,
                App.id.in_(select(AppMember.app_id).where(AppMember.user_id == actor_id)),
            )
        )

        if not include_archived:
            stmt = stmt.where(App.is_archived.is_(False))

        if search:
            term = f"%{search}%"
            stmt = stmt.where(or_(App.name.ilike(term), App.slug.ilike(term)))

        # Count against the same filters, before cursor/limit are applied —
        # the admin dashboard's "Активно"/"В разработке"/"Всего" card needs
        # the real filtered total here, not the schema's `None` default
        # (which the frontend coerced to 0, producing a negative "В
        # разработке" whenever the current page already had more published
        # apps than that fallback).
        total = (
            await self._db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()

        if cursor:
            cur_ts, cur_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    App.created_at > cur_ts,
                    (App.created_at == cur_ts) & (App.id > cur_id),
                )
            )

        stmt = stmt.limit(limit + 1)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = _encode_cursor(items[-1].id, items[-1].created_at) if has_more else None

        return CursorPage(
            items=[AppRead.model_validate(a) for a in items],
            next_cursor=next_cursor,
            has_more=has_more,
            total=total,
        )

    async def get_app(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> AppRead:
        app = await self._fetch_app(app_id)
        await self._require_member(app_id, actor_id)
        return AppRead.model_validate(app)

    async def create_app(
        self, data: AppCreate, owner_id: uuid.UUID, org_id: uuid.UUID | None = None
    ) -> AppRead:
        existing = await self._db.execute(select(App).where(App.slug == data.slug))
        if existing.scalar_one_or_none():
            raise AppConflictError(f"Slug already taken: {data.slug}")

        app = App(
            slug=data.slug,
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            category=data.category,
            settings=data.settings,
            owner_id=owner_id,
            org_id=org_id,
        )
        self._db.add(app)
        await self._db.flush()

        self._db.add(AppMember(app_id=app.id, user_id=owner_id, role="owner"))
        await self._db.flush()

        logger.info("app_created", app_id=str(app.id), slug=app.slug, owner=str(owner_id))
        return AppRead.model_validate(app)

    async def update_app(self, app_id: uuid.UUID, data: AppUpdate, actor_id: uuid.UUID) -> AppRead:
        app = await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin"})

        if data.name is not None:
            app.name = data.name
        if data.description is not None:
            app.description = data.description
        if data.icon is not None:
            app.icon = data.icon
        if data.color is not None:
            app.color = data.color
        if data.category is not None:
            app.category = data.category
        if data.settings is not None:
            app.settings = data.settings

        await self._db.flush()
        await self._db.refresh(app, attribute_names=["updated_at"])
        logger.info("app_updated", app_id=str(app_id))
        return AppRead.model_validate(app)

    async def delete_app(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        app = await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner"})
        app.is_archived = True
        await self._db.flush()
        logger.info("app_archived", app_id=str(app_id))

    async def check_publish(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> PublishCheckResult:
        """Dry-run the pre-publish integrity check (ТЗ 3.11.1) without
        publishing — lets the UI show issues before the user commits.
        Read access only (any member role), same as viewing the app itself."""
        await self._fetch_app(app_id)
        await self._require_member(app_id, actor_id)
        from app.services.publish_validation import PublishValidationService

        return await PublishValidationService(self._db).check(app_id)

    async def publish_app(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> AppRead:
        app = await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin"})

        from app.services.publish_validation import PublishValidationService

        check = await PublishValidationService(self._db).check(app_id)
        if not check.can_publish:
            raise AppPublishBlockedError(check.issues)

        app.is_published = True
        await self._db.flush()
        await self._db.refresh(app, attribute_names=["updated_at"])
        logger.info("app_published", app_id=str(app_id))
        return AppRead.model_validate(app)

    # ------------------------------------------------------------------
    # Clone
    # ------------------------------------------------------------------

    async def clone_app(
        self,
        app_id: uuid.UUID,
        data: AppCloneCreate,
        owner_id: uuid.UUID,
        org_id: uuid.UUID | None,
    ) -> AppRead:
        source = await self._fetch_app_with_entities(app_id)
        await self._require_member(app_id, owner_id)

        slug = data.slug or _slugify(data.name)
        existing = await self._db.execute(select(App).where(App.slug == slug))
        if existing.scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        new_app = App(
            slug=slug,
            name=data.name,
            description=source.description,
            icon=source.icon,
            color=source.color,
            category=source.category,
            settings=source.settings,
            owner_id=owner_id,
            org_id=org_id,
        )
        self._db.add(new_app)
        await self._db.flush()

        self._db.add(AppMember(app_id=new_app.id, user_id=owner_id, role="owner"))

        entity_id_map: dict[uuid.UUID, uuid.UUID] = {}
        field_id_map: dict[uuid.UUID, uuid.UUID] = {}

        for entity in source.entities:
            new_entity_id = uuid.uuid4()
            entity_id_map[entity.id] = new_entity_id

            new_entity = Entity(
                id=new_entity_id,
                app_id=new_app.id,
                slug=entity.slug,
                display_name=entity.display_name,
                name_plural=entity.name_plural,
                description=entity.description,
                icon=entity.icon,
                color=entity.color,
                settings=dict(entity.settings or {}),
                is_system=entity.is_system,
                field_order=[],
            )
            self._db.add(new_entity)
            await self._db.flush()

            new_field_ids: list[uuid.UUID] = []
            for field in entity.fields:
                new_field_id = uuid.uuid4()
                field_id_map[field.id] = new_field_id
                self._db.add(
                    Field(
                        id=new_field_id,
                        entity_id=new_entity_id,
                        app_id=new_app.id,
                        name=field.name,
                        display_name=field.display_name,
                        field_type=field.field_type,
                        is_required=field.is_required,
                        is_unique=field.is_unique,
                        is_system=field.is_system,
                        is_indexed=field.is_indexed,
                        default_value=dict(field.default_value) if field.default_value else None,
                        validation_rules=dict(field.validation_rules or {}),
                        field_options=dict(field.field_options or {}),
                        display_order=field.display_order,
                    )
                )
                new_field_ids.append(new_field_id)

            # Remap field_order
            remapped_order = [
                str(field_id_map.get(uuid.UUID(fid), uuid.UUID(fid)))
                for fid in (entity.field_order or [])
                if isinstance(fid, str)
            ]
            new_entity.field_order = remapped_order or [str(fid) for fid in new_field_ids]

        await self._db.flush()

        # Clone relations
        rel_result = await self._db.execute(select(Relation).where(Relation.app_id == app_id))
        for rel in rel_result.scalars().all():
            new_from = entity_id_map.get(rel.from_entity_id)
            new_to = entity_id_map.get(rel.to_entity_id)
            if new_from and new_to:
                self._db.add(
                    Relation(
                        app_id=new_app.id,
                        from_entity_id=new_from,
                        to_entity_id=new_to,
                        relation_type=rel.relation_type,
                        from_field_name=rel.from_field_name,
                        to_field_name=rel.to_field_name,
                        display_name=rel.display_name,
                        settings=dict(rel.settings or {}),
                    )
                )

        await self._db.flush()
        logger.info("app_cloned", source_id=str(app_id), new_id=str(new_app.id))
        return AppRead.model_validate(new_app)

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    async def create_snapshot(
        self,
        app_id: uuid.UUID,
        data: AppSnapshotCreate,
        actor_id: uuid.UUID,
    ) -> AppSnapshotRead:
        app = await self._fetch_app_with_entities(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin"})

        # Next sequential snapshot number for this app
        num_result = await self._db.execute(
            select(func.coalesce(func.max(AppSnapshot.snapshot_num), 0)).where(
                AppSnapshot.app_id == app_id
            )
        )
        next_num = (num_result.scalar() or 0) + 1

        snapshot_json: dict = {
            "app": {
                "name": app.name,
                "description": app.description,
                "icon": app.icon,
                "color": app.color,
                "category": app.category,
                "settings": dict(app.settings or {}),
            },
            "entities": [
                {
                    "id": str(entity.id),
                    "slug": entity.slug,
                    "display_name": entity.display_name,
                    "name_plural": entity.name_plural,
                    "description": entity.description,
                    "icon": entity.icon,
                    "color": entity.color,
                    "settings": dict(entity.settings or {}),
                    "is_system": entity.is_system,
                    "field_order": list(entity.field_order or []),
                    "fields": [
                        {
                            "id": str(f.id),
                            "name": f.name,
                            "display_name": f.display_name,
                            "field_type": f.field_type,
                            "is_required": f.is_required,
                            "is_unique": f.is_unique,
                            "is_system": f.is_system,
                            "is_indexed": f.is_indexed,
                            "default_value": dict(f.default_value) if f.default_value else None,
                            "validation_rules": dict(f.validation_rules or {}),
                            "field_options": dict(f.field_options or {}),
                            "display_order": f.display_order,
                        }
                        for f in entity.fields
                    ],
                }
                for entity in app.entities
            ],
        }

        snapshot = AppSnapshot(
            app_id=app_id,
            snapshot_num=next_num,
            snapshot_json=snapshot_json,
            created_by=actor_id,
            comment=data.comment,
        )
        self._db.add(snapshot)
        await self._db.flush()
        logger.info("snapshot_created", app_id=str(app_id), snapshot_num=next_num)
        return AppSnapshotRead.model_validate(snapshot)

    async def list_snapshots(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> list[AppSnapshotRead]:
        await self._fetch_app(app_id)
        await self._require_member(app_id, actor_id)
        result = await self._db.execute(
            select(AppSnapshot)
            .where(AppSnapshot.app_id == app_id)
            .order_by(AppSnapshot.snapshot_num.desc())
        )
        return [AppSnapshotRead.model_validate(s) for s in result.scalars().all()]

    async def rollback_snapshot(
        self,
        app_id: uuid.UUID,
        snapshot_num: int,
        actor_id: uuid.UUID,
    ) -> AppRead:
        app = await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin"})

        snap_result = await self._db.execute(
            select(AppSnapshot).where(
                AppSnapshot.app_id == app_id,
                AppSnapshot.snapshot_num == snapshot_num,
            )
        )
        snapshot = snap_result.scalar_one_or_none()
        if snapshot is None:
            raise AppNotFoundError(f"Snapshot #{snapshot_num} not found for app {app_id}")

        snap = snapshot.snapshot_json
        app_data = snap.get("app", {})
        app.name = app_data.get("name", app.name)
        app.description = app_data.get("description", app.description)
        app.icon = app_data.get("icon", app.icon)
        app.color = app_data.get("color", app.color)
        app.category = app_data.get("category", app.category)
        app.settings = app_data.get("settings", app.settings)
        app.version += 1

        # Delete all current entities (cascades to fields via FK)
        await self._db.execute(sa.delete(Entity).where(Entity.app_id == app_id))
        await self._db.flush()

        for entity_data in snap.get("entities", []):
            new_entity = Entity(
                id=uuid.UUID(entity_data["id"]),
                app_id=app_id,
                slug=entity_data["slug"],
                display_name=entity_data["display_name"],
                name_plural=entity_data.get("name_plural"),
                description=entity_data.get("description"),
                icon=entity_data.get("icon"),
                color=entity_data.get("color"),
                settings=dict(entity_data.get("settings") or {}),
                is_system=entity_data.get("is_system", False),
                field_order=list(entity_data.get("field_order") or []),
            )
            self._db.add(new_entity)
            await self._db.flush()

            for field_data in entity_data.get("fields", []):
                self._db.add(
                    Field(
                        id=uuid.UUID(field_data["id"]),
                        entity_id=new_entity.id,
                        app_id=app_id,
                        name=field_data["name"],
                        display_name=field_data["display_name"],
                        field_type=field_data["field_type"],
                        is_required=field_data.get("is_required", False),
                        is_unique=field_data.get("is_unique", False),
                        is_system=field_data.get("is_system", False),
                        is_indexed=field_data.get("is_indexed", False),
                        default_value=field_data.get("default_value"),
                        validation_rules=dict(field_data.get("validation_rules") or {}),
                        field_options=dict(field_data.get("field_options") or {}),
                        display_order=field_data.get("display_order", 0),
                    )
                )

        await self._db.flush()
        await self._db.refresh(app)
        logger.info("app_rolled_back", app_id=str(app_id), to_snapshot=snapshot_num)
        return AppRead.model_validate(app)

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def list_members(
        self,
        app_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> list[AppMemberRead]:
        await self._fetch_app(app_id)
        await self._require_member(app_id, actor_id)
        rows = await self._db.execute(
            select(AppMember, User)
            .join(User, User.id == AppMember.user_id)
            .where(AppMember.app_id == app_id)
            .order_by(AppMember.granted_at)
        )
        result = []
        for member, user in rows.all():
            result.append(
                AppMemberRead(
                    user_id=member.user_id,
                    role=member.role,
                    granted_at=member.granted_at,
                    email=user.email,
                    display_name=user.display_name,
                )
            )
        return result

    async def add_member(
        self,
        app_id: uuid.UUID,
        data: AppMemberAdd,
        actor_id: uuid.UUID,
    ) -> None:
        await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin"})

        existing = await self._db.execute(
            select(AppMember).where(AppMember.app_id == app_id, AppMember.user_id == data.user_id)
        )
        member = existing.scalar_one_or_none()
        if member:
            member.role = data.role
        else:
            self._db.add(
                AppMember(
                    app_id=app_id,
                    user_id=data.user_id,
                    role=data.role,
                    granted_by=actor_id,
                )
            )
        await self._db.flush()

    async def remove_member(
        self,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> None:
        await self._require_role(app_id, actor_id, {"owner", "admin"})
        result = await self._db.execute(
            select(AppMember).where(AppMember.app_id == app_id, AppMember.user_id == user_id)
        )
        member = result.scalar_one_or_none()
        if member:
            await self._db.delete(member)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fetch_app(self, app_id: uuid.UUID) -> App:
        result = await self._db.execute(select(App).where(App.id == app_id))
        app = result.scalar_one_or_none()
        if app is None:
            raise AppNotFoundError(str(app_id))
        return app

    async def _fetch_app_with_entities(self, app_id: uuid.UUID) -> App:
        result = await self._db.execute(
            select(App)
            .where(App.id == app_id)
            .options(selectinload(App.entities).selectinload(Entity.fields))
        )
        app = result.scalar_one_or_none()
        if app is None:
            raise AppNotFoundError(str(app_id))
        return app

    async def require_member(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        """Public entry point for endpoints that need a bare membership
        check (any role) without fetching/returning the app itself — e.g.
        the edit-lock status endpoint."""
        await self._fetch_app(app_id)
        await self._require_member(app_id, actor_id)

    async def require_edit_access(self, app_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        """Public entry point for endpoints gating on 'can edit this app's
        content' (owner/admin/editor) — e.g. acquiring/releasing the edit
        lock. Mirrors the role set ModuleService uses for the same concept."""
        await self._fetch_app(app_id)
        await self._require_role(app_id, actor_id, {"owner", "admin", "editor"})

    async def _require_member(self, app_id: uuid.UUID, user_id: uuid.UUID) -> None:
        result = await self._db.execute(
            select(AppMember).where(AppMember.app_id == app_id, AppMember.user_id == user_id)
        )
        if result.scalar_one_or_none() is None:
            raise AppNotFoundError(str(app_id))

    async def _require_role(self, app_id: uuid.UUID, user_id: uuid.UUID, allowed: set[str]) -> None:
        result = await self._db.execute(
            select(AppMember).where(AppMember.app_id == app_id, AppMember.user_id == user_id)
        )
        member = result.scalar_one_or_none()
        if member is None or member.role not in allowed:
            raise AppPermissionError(f"Role {member.role if member else 'none'!r} not in {allowed}")
