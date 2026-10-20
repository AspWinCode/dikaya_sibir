"""`update_record` action combined with a `lookup(agg=sum)` value — an
automation rule that writes an aggregated value from one table into a
related record in another table (e.g. "сумма операций по работнику":
table Б has a direct relation to table А, and each new/changed Б row
should recompute the SUM over all its siblings into А's own field).

Exercises the real end-to-end path through
app.worker.tasks.sandbox.execute_rules_batch — including the new
lookup-resolution pre-pass (app.engine.lookup.resolve_rule_lookups) that
runs before the pure interpreter, since automation-rule actions previously
had no way to reference another table's aggregated data at all (lookups
only worked inside validation-rule conditions).
"""

import asyncio
import os
import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.models.data import Record
from app.worker.tasks.sandbox import execute_rules_batch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://app_user:app_pass@localhost:5433/nocode_test",
)


def _run_execute_rules_batch(rules: list[dict], context: dict, batch_id: str) -> dict:
    # Same reasoning as test_rules_upsert.py's _run_persist_batch: the task
    # does its own asyncio.run() internally (a real Celery worker has no
    # loop of its own between invocations), so it can't be awaited directly
    # from inside pytest-asyncio's already-running loop — run it in a
    # separate thread, same as Celery's own prefork/thread model would.
    return execute_rules_batch(rules=rules, context=context, execution_batch_id=batch_id)


async def _execute(rules: list[dict], context: dict, batch_id: str) -> dict:
    return await asyncio.to_thread(_run_execute_rules_batch, rules, context, batch_id)


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    # Unique email per run: this test commits (see `tables`' docstring), so
    # the usual rollback-at-teardown isolation (tests/conftest.py's
    # db_session fixture) doesn't clean this row up — a fixed email would
    # collide with a leftover row the moment this test runs a second time
    # against the same (tmpfs, but long-lived across `docker compose run`
    # invocations) test database.
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="Builder", is_system=True))
    user = User(
        email=f"lookup_action_builder_{uuid.uuid4().hex[:8]}@example.com",
        display_name="Builder",
        password_hash=hash_password("Build1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


@pytest.fixture()
async def tables(client: AsyncClient, builder: User, db_session: AsyncSession) -> dict:
    """Table А ("rabotniki": работник, общая_сумма) and table Б
    ("operatsii_b": id_tablicy_a, stoimost) — exactly the shape from the
    user's own example.

    Commits after creating all fixture data: execute_rules_batch's lookup
    resolution and _persist_batch each open their own, separate DB
    connection (see their docstrings — a Celery worker has no event loop/
    session of its own between invocations), so anything created only
    through this test's `db_session` (flushed, never committed until the
    fixture's own teardown rollback) would otherwise be invisible to them
    under READ COMMITTED — not a race, a structural requirement of this
    cross-connection setup.
    """
    token = await _login(client, builder.email, "Build1234!")
    headers = {"Authorization": f"Bearer {token}"}
    app_resp = await client.post(
        "/api/v1/apps",
        json={"slug": f"lookup-action-app-{uuid.uuid4().hex[:6]}", "name": "Lookup Action Test App"},
        headers=headers,
    )
    app_id = app_resp.json()["id"]

    a_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "rabotniki", "display_name": "Работники"},
        headers=headers,
    )
    a_entity_id = a_resp.json()["id"]
    for f in [
        {"name": "rabotnik", "display_name": "Работник", "field_type": "text"},
        {"name": "obschaya_summa", "display_name": "Общая сумма", "field_type": "decimal"},
    ]:
        await client.post(
            f"/api/v1/apps/{app_id}/entities/{a_entity_id}/fields", json=f, headers=headers
        )

    b_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "operatsii_b", "display_name": "Операции"},
        headers=headers,
    )
    b_entity_id = b_resp.json()["id"]
    for f in [
        {"name": "id_tablicy_a", "display_name": "ID Таблицы А", "field_type": "text"},
        {"name": "stoimost", "display_name": "Стоимость", "field_type": "decimal"},
    ]:
        await client.post(
            f"/api/v1/apps/{app_id}/entities/{b_entity_id}/fields", json=f, headers=headers
        )

    a_record = await client.post(
        f"/api/v1/apps/{app_id}/entities/{a_entity_id}/records",
        json={"payload": {"rabotnik": "Иванов", "obschaya_summa": "0"}},
        headers=headers,
    )
    a_record_id = a_record.json()["id"]
    await db_session.commit()

    # No explicit cleanup: this fixture commits (see docstring above), so
    # the usual rollback-at-teardown isolation (tests/conftest.py's
    # db_session fixture) doesn't apply to these rows. Harmless to leave —
    # docker-compose.test.yml's whole point is a disposable tmpfs Postgres
    # torn down (`down -v`) after every real test run, and every
    # identifier here (builder's email, the app's slug) is randomized per
    # run specifically so repeated interactive runs against the same
    # still-up container don't collide either.
    return {
        "app_id": app_id,
        "a_entity_id": a_entity_id,
        "b_entity_id": b_entity_id,
        "a_record_id": a_record_id,
        "headers": headers,
        "client": client,
    }


def _update_record_rule(b_entity_id: str) -> dict:
    """ЕСЛИ (всегда) → обновить связанную запись в А: общая_сумма = SUM
    стоимости по всем операциям Б с тем же id_tablicy_a."""
    return {
        "id": str(uuid.uuid4()),
        "trigger": {"event": "record.created", "watch_fields": []},
        "conditions": {},
        "actions": [
            {
                "type": "update_record",
                "record_id_field": "id_tablicy_a",
                "payload": {
                    "obschaya_summa": {
                        "type": "lookup",
                        "entity_id": b_entity_id,
                        "filter": {
                            "id_tablicy_a": {"type": "field_ref", "field": "id_tablicy_a"},
                        },
                        "agg": "sum",
                        "field": "stoimost",
                    },
                },
            },
        ],
        "priority": 10,
    }


@pytest.mark.asyncio
async def test_update_record_action_writes_a_lookup_sum_into_the_related_record(
    db_session: AsyncSession, tables: dict
) -> None:
    headers = tables["headers"]
    client = tables["client"]
    app_id = tables["app_id"]
    b_entity_id = tables["b_entity_id"]
    a_record_id = tables["a_record_id"]

    rule = _update_record_rule(b_entity_id)

    # First operation: 200 — triggers the rule once, sum so far is 200.
    b1 = await client.post(
        f"/api/v1/apps/{app_id}/entities/{b_entity_id}/records",
        json={"payload": {"id_tablicy_a": a_record_id, "stoimost": "200"}},
        headers=headers,
    )
    b1_id = b1.json()["id"]
    await db_session.commit()
    result1 = await _execute(
        [rule],
        {
            "record": {"id_tablicy_a": a_record_id, "stoimost": "200"},
            "entity_id": b_entity_id,
            "app_id": app_id,
            "event": "record.created",
            "record_id": b1_id,
        },
        "batch-1",
    )
    assert result1["status"] == "success", result1

    db_session.expire_all()
    a_row = (await db_session.execute(select(Record).where(Record.id == uuid.UUID(a_record_id)))).scalar_one()
    assert a_row.payload["obschaya_summa"] == 200.0

    # Second operation: another 200 — the rule recomputes the SUM over both
    # rows (self-correcting, not an increment), so it reads 400, not 600.
    b2 = await client.post(
        f"/api/v1/apps/{app_id}/entities/{b_entity_id}/records",
        json={"payload": {"id_tablicy_a": a_record_id, "stoimost": "200"}},
        headers=headers,
    )
    b2_id = b2.json()["id"]
    await db_session.commit()
    result2 = await _execute(
        [rule],
        {
            "record": {"id_tablicy_a": a_record_id, "stoimost": "200"},
            "entity_id": b_entity_id,
            "app_id": app_id,
            "event": "record.created",
            "record_id": b2_id,
        },
        "batch-2",
    )
    assert result2["status"] == "success", result2

    db_session.expire_all()
    a_row = (await db_session.execute(select(Record).where(Record.id == uuid.UUID(a_record_id)))).scalar_one()
    assert a_row.payload["obschaya_summa"] == 400.0
