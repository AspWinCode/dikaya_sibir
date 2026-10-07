"""The `create_record` action's `match`/`increment` upsert extension (ТЗ
item 13's building block for running-balance entities, e.g. a
Product×Location stock table fed by receipt/transfer records).

Exercises the real persistence path (app.worker.tasks.sandbox._persist_batch)
rather than just the pure interpreter, since the find-or-increment logic
lives there (DB access is deliberately kept out of the interpreter — see
its module docstring).
"""

import asyncio
import os
import uuid

import pytest
from app.core.security import hash_password
from app.engine.interpreter import BatchResult, ExecutionContext
from app.models.data import Record
from app.models.identity import Role, User, UserRole
from app.worker.tasks.sandbox import _persist_batch
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://app_user:app_pass@localhost:5433/nocode_test",
)


def _run_persist_batch(batch: BatchResult, ctx: ExecutionContext, batch_id: str) -> None:
    """_persist_batch (like the Celery task that normally calls it) does its
    own `asyncio.run()` — by design, since a real Celery worker process has
    no event loop of its own yet. That means it can't be awaited from
    inside pytest-asyncio's already-running loop; called via
    asyncio.to_thread at the call site instead, same as it would run in
    Celery's own thread/process in production. It needs its own,
    never-before-used engine (monkeypatched onto app.core.database) rather
    than the test suite's shared `test_engine` — that one's connections are
    already bound to pytest's main loop from `client`/`db_session` usage
    earlier in the same test, and asyncpg connections are loop-bound.
    """
    import app.core.database as db_module

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    original = db_module.AsyncSessionLocal
    db_module.AsyncSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    try:
        _persist_batch(batch, ctx, batch_id)
    finally:
        db_module.AsyncSessionLocal = original
        asyncio.run(engine.dispose())


async def _persist(batch: BatchResult, ctx: ExecutionContext, batch_id: str) -> None:
    await asyncio.to_thread(_run_persist_batch, batch, ctx, batch_id)


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="Builder", is_system=True))
    user = User(
        email="upsert_builder@example.com",
        display_name="Builder",
        password_hash=hash_password("Build1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


@pytest.fixture()
async def balance_entity_id(client: AsyncClient, builder: User) -> uuid.UUID:
    """A minimal Product×Location balance entity, created through the real
    API exactly like the app builder would."""
    token = await _login(client, builder.email, "Build1234!")
    headers = {"Authorization": f"Bearer {token}"}
    app_resp = await client.post(
        "/api/v1/apps",
        json={"slug": f"upsert-app-{uuid.uuid4().hex[:6]}", "name": "Upsert Test App"},
        headers=headers,
    )
    app_id = app_resp.json()["id"]
    entity_resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "ostatki", "display_name": "Остатки"},
        headers=headers,
    )
    entity_id = entity_resp.json()["id"]
    for f in [
        {"name": "product_id", "display_name": "Товар", "field_type": "text"},
        {"name": "location_id", "display_name": "Помещение", "field_type": "text"},
        {"name": "quantity", "display_name": "Количество", "field_type": "decimal"},
    ]:
        await client.post(
            f"/api/v1/apps/{app_id}/entities/{entity_id}/fields", json=f, headers=headers
        )
    return uuid.UUID(entity_id)


def _ctx(balance_entity_id: uuid.UUID) -> ExecutionContext:
    return ExecutionContext(
        record={},
        entity_id=balance_entity_id,
        app_id=uuid.uuid4(),
        event="record.created",
    )


@pytest.mark.asyncio
async def test_upsert_creates_a_new_balance_row_when_none_matches(
    db_session: AsyncSession, balance_entity_id: uuid.UUID
) -> None:
    batch = BatchResult(
        records_to_create=[
            {
                "entity_id": str(balance_entity_id),
                "payload": {"product_id": "prod-1", "location_id": "loc-1", "quantity": 10},
                "match": {"product_id": "prod-1", "location_id": "loc-1"},
                "increment": {"quantity": 10},
            }
        ]
    )
    await _persist(batch, _ctx(balance_entity_id), "batch-1")

    rows = (
        (await db_session.execute(select(Record).where(Record.entity_id == balance_entity_id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].payload["quantity"] == 10


@pytest.mark.asyncio
async def test_upsert_increments_the_existing_row_instead_of_duplicating(
    db_session: AsyncSession, balance_entity_id: uuid.UUID
) -> None:
    ctx = _ctx(balance_entity_id)
    action = {
        "entity_id": str(balance_entity_id),
        "match": {"product_id": "prod-2", "location_id": "loc-A"},
        "increment": {"quantity": 5},
    }

    # First receipt: +5 at loc-A — no row exists yet, creates one.
    await _persist(
        BatchResult(
            records_to_create=[
                {
                    **action,
                    "payload": {"product_id": "prod-2", "location_id": "loc-A", "quantity": 5},
                }
            ]
        ),
        ctx,
        "batch-2a",
    )
    # Second receipt: +5 more at the same product/location.
    await _persist(BatchResult(records_to_create=[action]), ctx, "batch-2b")

    rows = (
        (
            await db_session.execute(
                select(Record).where(
                    Record.entity_id == balance_entity_id, Record.is_deleted.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1  # not duplicated
    assert rows[0].payload["quantity"] == 10  # 5 + 5
    assert rows[0].version == 2  # incremented, not recreated


@pytest.mark.asyncio
async def test_upsert_treats_different_locations_as_different_balance_rows(
    db_session: AsyncSession, balance_entity_id: uuid.UUID
) -> None:
    """A transfer's two sides (decrement source, increment destination) must
    not collide into one row just because the product matches."""
    ctx = _ctx(balance_entity_id)

    await _persist(
        BatchResult(
            records_to_create=[
                {
                    "entity_id": str(balance_entity_id),
                    "payload": {
                        "product_id": "prod-3",
                        "location_id": "warehouse-A",
                        "quantity": 20,
                    },
                    "match": {"product_id": "prod-3", "location_id": "warehouse-A"},
                    "increment": {"quantity": 20},
                }
            ]
        ),
        ctx,
        "batch-3a",
    )

    # Transfer 8 units from A to B: decrement A, increment (create) B.
    await _persist(
        BatchResult(
            records_to_create=[
                {
                    "entity_id": str(balance_entity_id),
                    "payload": {
                        "product_id": "prod-3",
                        "location_id": "warehouse-A",
                        "quantity": -8,
                    },
                    "match": {"product_id": "prod-3", "location_id": "warehouse-A"},
                    "increment": {"quantity": -8},
                },
                {
                    "entity_id": str(balance_entity_id),
                    "payload": {
                        "product_id": "prod-3",
                        "location_id": "warehouse-B",
                        "quantity": 8,
                    },
                    "match": {"product_id": "prod-3", "location_id": "warehouse-B"},
                    "increment": {"quantity": 8},
                },
            ]
        ),
        ctx,
        "batch-3b",
    )

    rows = (
        (
            await db_session.execute(
                select(Record).where(
                    Record.entity_id == balance_entity_id, Record.is_deleted.is_(False)
                )
            )
        )
        .scalars()
        .all()
    )
    by_location = {r.payload["location_id"]: r.payload["quantity"] for r in rows}
    assert by_location == {"warehouse-A": 12, "warehouse-B": 8}
