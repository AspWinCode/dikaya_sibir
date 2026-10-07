import uuid

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Group, GroupRole, UserGroup, UserRole
from app.schemas.groups import (
    GroupCreate,
    GroupDetailRead,
    GroupMemberRead,
    GroupRead,
    GroupUpdate,
)
from app.schemas.users import RoleRead

logger = structlog.get_logger(__name__)


class GroupNotFoundError(Exception):
    pass


class GroupConflictError(Exception):
    pass


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_groups(self) -> list[GroupRead]:
        result = await self._db.execute(select(Group).order_by(Group.name))
        groups = result.scalars().all()
        return [self._to_read(g) for g in groups]

    async def get_group(self, group_id: uuid.UUID) -> GroupDetailRead:
        g = await self._fetch(group_id)
        return self._to_detail(g)

    async def create_group(self, data: GroupCreate) -> GroupDetailRead:
        existing = await self._db.execute(select(Group).where(Group.name == data.name))
        if existing.scalar_one_or_none() is not None:
            raise GroupConflictError(f"Группа с именем «{data.name}» уже существует")

        group = Group(name=data.name, description=data.description)
        self._db.add(group)
        await self._db.flush()

        for role_id in data.role_ids:
            self._db.add(GroupRole(group_id=group.id, role_id=role_id))
        await self._db.flush()

        await self._db.refresh(group)
        logger.info("group_created", group_id=str(group.id), name=group.name)
        return self._to_detail(group)

    async def update_group(self, group_id: uuid.UUID, data: GroupUpdate) -> GroupDetailRead:
        group = await self._fetch(group_id)

        if data.name is not None and data.name != group.name:
            existing = await self._db.execute(select(Group).where(Group.name == data.name))
            if existing.scalar_one_or_none() is not None:
                raise GroupConflictError(f"Группа с именем «{data.name}» уже существует")
            group.name = data.name

        if data.description is not None:
            group.description = data.description

        if data.role_ids is not None:
            await self._db.execute(delete(GroupRole).where(GroupRole.group_id == group_id))
            for role_id in data.role_ids:
                self._db.add(GroupRole(group_id=group_id, role_id=role_id))

        await self._db.flush()
        await self._db.refresh(group)
        return self._to_detail(group)

    async def delete_group(self, group_id: uuid.UUID) -> None:
        group = await self._fetch(group_id)
        await self._db.delete(group)
        await self._db.flush()
        logger.info("group_deleted", group_id=str(group_id))

    async def add_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._fetch(group_id)
        existing = await self._db.execute(
            select(UserGroup).where(UserGroup.group_id == group_id, UserGroup.user_id == user_id)
        )
        if existing.scalar_one_or_none() is None:
            self._db.add(UserGroup(group_id=group_id, user_id=user_id))
            await self._db.flush()

    async def remove_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._fetch(group_id)
        await self._db.execute(
            delete(UserGroup).where(UserGroup.group_id == group_id, UserGroup.user_id == user_id)
        )
        await self._db.flush()

    async def apply_roles_to_members(
        self, group_id: uuid.UUID, granted_by: uuid.UUID | None = None
    ) -> int:
        """Grant all group roles to every group member. Returns count of new grants."""
        group = await self._fetch(group_id)
        role_ids = [r.id for r in group.roles]
        if not role_ids:
            return 0

        count = 0
        for member in group.members:
            existing_roles = {ur.role_id for ur in member.user_roles}
            for role_id in role_ids:
                if role_id not in existing_roles:
                    self._db.add(
                        UserRole(user_id=member.id, role_id=role_id, granted_by=granted_by)
                    )
                    count += 1
        await self._db.flush()
        logger.info("group_roles_applied", group_id=str(group_id), grants=count)
        return count

    # ------------------------------------------------------------------
    async def _fetch(self, group_id: uuid.UUID) -> Group:
        result = await self._db.execute(select(Group).where(Group.id == group_id))
        group = result.scalar_one_or_none()
        if group is None:
            raise GroupNotFoundError(str(group_id))
        return group

    @staticmethod
    def _to_read(g: Group) -> GroupRead:
        return GroupRead(
            id=g.id,
            name=g.name,
            description=g.description,
            created_at=g.created_at,
            member_count=len(g.members),
            roles=[RoleRead(id=r.id, display_name=r.display_name) for r in g.roles],
        )

    @staticmethod
    def _to_detail(g: Group) -> GroupDetailRead:
        return GroupDetailRead(
            id=g.id,
            name=g.name,
            description=g.description,
            created_at=g.created_at,
            member_count=len(g.members),
            roles=[RoleRead(id=r.id, display_name=r.display_name) for r in g.roles],
            members=[
                GroupMemberRead(
                    id=m.id,
                    email=m.email,
                    display_name=m.display_name,
                    is_active=m.is_active,
                )
                for m in g.members
            ],
        )
