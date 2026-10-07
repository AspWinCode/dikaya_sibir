"""
Row-level ABAC (AbacRule) — condition grammar and enforcement.

Unit:
  - abac.validate_condition accepts/rejects condition shapes
  - abac.condition_to_sql builds clauses for every supported op/field/token

Integration (db_session):
  - RecordService enforces AbacRule scope on list/get/update/delete, not just
    listing (ТЗ 3.1.4: "видимость и редактируемость")
  - "$self.org_id" resolves the acting user's organisation
  - "deny" wins over "allow"
"""

import uuid

import pytest
from app.models.data import Record
from app.models.identity import AbacRule, Organisation, Role, User
from app.schemas.records import RecordListParams, RecordUpdate
from app.services import abac
from app.services.records import RecordNotFoundError, RecordService
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Unit: condition validation
# ==================================================================


class TestValidateCondition:
    def test_accepts_author_self(self) -> None:
        abac.validate_condition({"field": "created_by", "op": "eq", "value": "$self"})

    def test_accepts_payload_field_vs_self_org(self) -> None:
        abac.validate_condition({"field": "department_id", "op": "eq", "value": "$self.org_id"})

    def test_accepts_literal_in_list(self) -> None:
        abac.validate_condition({"field": "status", "op": "in", "value": ["draft", "approved"]})

    def test_rejects_missing_field(self) -> None:
        with pytest.raises(abac.AbacConditionError):
            abac.validate_condition({"op": "eq", "value": "x"})

    def test_rejects_unknown_op(self) -> None:
        with pytest.raises(abac.AbacConditionError):
            abac.validate_condition({"field": "status", "op": "regex", "value": "x"})

    def test_rejects_non_list_value_for_in(self) -> None:
        with pytest.raises(abac.AbacConditionError):
            abac.validate_condition({"field": "status", "op": "in", "value": "draft"})

    def test_rejects_unknown_self_attribute(self) -> None:
        with pytest.raises(abac.AbacConditionError):
            abac.validate_condition(
                {"field": "department_id", "op": "eq", "value": "$self.department"}
            )

    def test_rejects_range_op_on_author_field(self) -> None:
        with pytest.raises(abac.AbacConditionError):
            abac.validate_condition({"field": "created_by", "op": "gt", "value": "1"})


# ==================================================================
# Unit: condition -> SQL
# ==================================================================


class TestConditionToSql:
    def _ctx(self, actor_id: uuid.UUID, org_id: str | None = "org-1") -> dict:
        return {"id": str(actor_id), "org_id": org_id}

    def test_author_field_self_token(self) -> None:
        actor = uuid.uuid4()
        clause = abac.condition_to_sql(
            {"field": "created_by", "op": "eq", "value": "$self"},
            self._ctx(actor),
            record_model=Record,
        )
        assert clause is not None

    def test_payload_field_literal(self) -> None:
        clause = abac.condition_to_sql(
            {"field": "department_id", "op": "eq", "value": "dept-42"},
            self._ctx(uuid.uuid4()),
            record_model=Record,
        )
        assert clause is not None

    def test_payload_field_self_org(self) -> None:
        clause = abac.condition_to_sql(
            {"field": "department_id", "op": "eq", "value": "$self.org_id"},
            self._ctx(uuid.uuid4()),
            record_model=Record,
        )
        assert clause is not None

    def test_unresolvable_self_org_returns_none(self) -> None:
        """Actor has no organisation (org_id=None in context) -> can't evaluate."""
        clause = abac.condition_to_sql(
            {"field": "department_id", "op": "eq", "value": "$self.org_id"},
            self._ctx(uuid.uuid4(), org_id=None),
            record_model=Record,
        )
        assert clause is None

    def test_numeric_ops(self) -> None:
        for op in ("gt", "gte", "lt", "lte"):
            clause = abac.condition_to_sql(
                {"field": "amount", "op": op, "value": "500"},
                self._ctx(uuid.uuid4()),
                record_model=Record,
            )
            assert clause is not None, op

    def test_non_numeric_value_on_range_op_returns_none(self) -> None:
        clause = abac.condition_to_sql(
            {"field": "amount", "op": "gt", "value": "not-a-number"},
            self._ctx(uuid.uuid4()),
            record_model=Record,
        )
        assert clause is None

    def test_unsupported_op_returns_none(self) -> None:
        clause = abac.condition_to_sql(
            {"field": "status", "op": "regex", "value": "x"},
            self._ctx(uuid.uuid4()),
            record_model=Record,
        )
        assert clause is None


# ==================================================================
# Integration: RecordService enforcement
# ==================================================================


@pytest.fixture()
async def scoped_role(db_session: AsyncSession) -> Role:
    role_id = f"scoped_{uuid.uuid4().hex[:6]}"
    role = Role(id=role_id, display_name="Scoped role", is_system=False)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture()
async def org(db_session: AsyncSession) -> Organisation:
    suffix = uuid.uuid4().hex[:6]
    org = Organisation(slug=f"org-{suffix}", display_name=f"Org {suffix}")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture()
async def actor(db_session: AsyncSession, org: Organisation) -> User:
    user = User(
        email=f"abac_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Abac Actor",
        org_id=org.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_record(
    db_session: AsyncSession, entity_id: uuid.UUID, payload: dict, created_by: uuid.UUID
) -> Record:
    record = Record(entity_id=entity_id, payload=payload, created_by=created_by)
    db_session.add(record)
    await db_session.flush()
    return record


@pytest.mark.integration
@pytest.mark.asyncio
async def test_author_self_rule_scopes_list(
    db_session: AsyncSession, scoped_role: Role, actor: User
) -> None:
    entity_id = uuid.uuid4()
    other_user = uuid.uuid4()
    mine = await _make_record(db_session, entity_id, {"title": "mine"}, actor.id)
    await _make_record(db_session, entity_id, {"title": "not mine"}, other_user)

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    page = await svc.list_records(
        entity_id,
        RecordListParams(),
        actor_id=actor.id,
        actor_roles=[scoped_role.id],
    )
    ids = {r.id for r in page.items}
    assert ids == {mine.id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_self_org_rule_scopes_by_department_field(
    db_session: AsyncSession,
    scoped_role: Role,
    actor: User,
    org: Organisation,
) -> None:
    """ТЗ 3.1.4 example: 'пользователь видит только записи своего отдела' —
    modelled here as a payload field equal to the acting user's org_id."""
    entity_id = uuid.uuid4()
    same_org = await _make_record(
        db_session, entity_id, {"department_id": str(org.id)}, uuid.uuid4()
    )
    await _make_record(db_session, entity_id, {"department_id": str(uuid.uuid4())}, uuid.uuid4())

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "department_id", "op": "eq", "value": "$self.org_id"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    page = await svc.list_records(
        entity_id,
        RecordListParams(),
        actor_id=actor.id,
        actor_roles=[scoped_role.id],
    )
    ids = {r.id for r in page.items}
    assert ids == {same_org.id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deny_rule_wins_over_allow(
    db_session: AsyncSession, scoped_role: Role, actor: User
) -> None:
    entity_id = uuid.uuid4()
    blocked = await _make_record(db_session, entity_id, {"status": "secret"}, actor.id)

    db_session.add_all(
        [
            AbacRule(
                role_id=scoped_role.id,
                resource_type="entity",
                resource_id=None,
                condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
                effect="allow",
            ),
            AbacRule(
                role_id=scoped_role.id,
                resource_type="entity",
                resource_id=None,
                condition_json=[{"field": "status", "op": "eq", "value": "secret"}],
                effect="deny",
            ),
        ]
    )
    await db_session.flush()

    svc = RecordService(db_session)
    page = await svc.list_records(
        entity_id,
        RecordListParams(),
        actor_id=actor.id,
        actor_roles=[scoped_role.id],
    )
    assert blocked.id not in {r.id for r in page.items}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_record_out_of_scope_raises_not_found(
    db_session: AsyncSession,
    scoped_role: Role,
    actor: User,
) -> None:
    entity_id = uuid.uuid4()
    other = await _make_record(db_session, entity_id, {"title": "not mine"}, uuid.uuid4())

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    with pytest.raises(RecordNotFoundError):
        await svc.get_record(entity_id, other.id, actor_id=actor.id, actor_roles=[scoped_role.id])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_record_out_of_scope_is_blocked(
    db_session: AsyncSession,
    scoped_role: Role,
    actor: User,
) -> None:
    """A record hidden by ABAC can't be edited either — not just hidden from lists."""
    entity_id = uuid.uuid4()
    app_id = uuid.uuid4()
    other = await _make_record(db_session, entity_id, {"title": "not mine"}, uuid.uuid4())

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    with pytest.raises(RecordNotFoundError):
        await svc.update_record(
            entity_id,
            other.id,
            RecordUpdate(payload={"title": "hacked"}),
            app_id,
            actor_id=actor.id,
            actor_roles=[scoped_role.id],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_record_out_of_scope_is_blocked(
    db_session: AsyncSession,
    scoped_role: Role,
    actor: User,
) -> None:
    entity_id = uuid.uuid4()
    other = await _make_record(db_session, entity_id, {"title": "not mine"}, uuid.uuid4())

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    with pytest.raises(RecordNotFoundError):
        await svc.delete_record(
            entity_id, other.id, actor_id=actor.id, actor_roles=[scoped_role.id]
        )

    # record must still exist, untouched
    fetched = await svc.get_record(entity_id, other.id)
    assert fetched.payload["title"] == "not mine"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_record_in_scope_succeeds(
    db_session: AsyncSession,
    scoped_role: Role,
    actor: User,
) -> None:
    entity_id = uuid.uuid4()
    app_id = uuid.uuid4()
    mine = await _make_record(db_session, entity_id, {"title": "mine"}, actor.id)

    db_session.add(
        AbacRule(
            role_id=scoped_role.id,
            resource_type="entity",
            resource_id=None,
            condition_json=[{"field": "created_by", "op": "eq", "value": "$self"}],
            effect="allow",
        )
    )
    await db_session.flush()

    svc = RecordService(db_session)
    updated = await svc.update_record(
        entity_id,
        mine.id,
        RecordUpdate(payload={"title": "updated"}),
        app_id,
        actor_id=actor.id,
        actor_roles=[scoped_role.id],
    )
    assert updated.payload["title"] == "updated"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_matching_rules_is_open_by_default(
    db_session: AsyncSession, scoped_role: Role, actor: User
) -> None:
    entity_id = uuid.uuid4()
    rec = await _make_record(db_session, entity_id, {"title": "anything"}, uuid.uuid4())

    svc = RecordService(db_session)
    page = await svc.list_records(
        entity_id,
        RecordListParams(),
        actor_id=actor.id,
        actor_roles=[scoped_role.id],
    )
    assert rec.id in {r.id for r in page.items}
