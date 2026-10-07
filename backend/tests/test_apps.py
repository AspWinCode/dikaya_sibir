"""App CRUD + entity/field management integration tests."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Role, User, UserRole


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
async def builder_user(db_session: AsyncSession) -> User:
    for role_id in ("app_builder", "platform_admin"):
        existing = await db_session.get(Role, role_id)
        if not existing:
            db_session.add(Role(id=role_id, display_name=role_id.replace("_", " ").title(), is_system=True))

    user = User(
        email="builder@example.com",
        display_name="Builder",
        password_hash=hash_password("Builder1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _auth(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ------------------------------------------------------------------
# App CRUD
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_app(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    resp = await client.post(
        "/api/v1/apps",
        json={"slug": "crm-app", "name": "CRM"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["slug"] == "crm-app"
    assert data["owner_id"] == str(builder_user.id)
    assert data["is_published"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_app_duplicate_slug(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    payload = {"slug": "dup-slug", "name": "Dup"}
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/apps", json=payload, headers=headers)
    resp = await client.post("/api/v1/apps", json=payload, headers=headers)
    assert resp.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_apps_only_own(client: AsyncClient, db_session: AsyncSession, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/apps", json={"slug": "my-app", "name": "My App"}, headers=headers)

    resp = await client.get("/api/v1/apps", headers=headers)
    assert resp.status_code == 200
    slugs = [a["slug"] for a in resp.json()["items"]]
    assert "my-app" in slugs


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publish_app(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post("/api/v1/apps", json={"slug": "pub-app", "name": "Pub"}, headers=headers)
    app_id = create.json()["id"]

    resp = await client.post(f"/api/v1/apps/{app_id}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_published"] is True


# ------------------------------------------------------------------
# Entity management
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_entity_auto_system_fields(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    create_app = await client.post(
        "/api/v1/apps", json={"slug": "ent-app", "name": "Ent App"}, headers=headers
    )
    app_id = create_app.json()["id"]

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "invoice", "display_name": "Invoice"},
        headers=headers,
    )
    assert resp.status_code == 201
    entity = resp.json()
    assert entity["slug"] == "invoice"

    # System fields id, created_at, updated_at must be auto-created
    field_names = [f["name"] for f in entity["fields"]]
    assert "id" in field_names
    assert "created_at" in field_names
    assert "updated_at" in field_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_custom_field(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    app = await client.post("/api/v1/apps", json={"slug": "field-app", "name": "Field App"}, headers=headers)
    app_id = app.json()["id"]

    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "order", "display_name": "Order"},
        headers=headers,
    )
    entity_id = entity.json()["id"]

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "total_amount", "display_name": "Total Amount", "field_type": "decimal"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "total_amount"
    assert resp.json()["field_type"] == "decimal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cannot_delete_system_field(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    app = await client.post("/api/v1/apps", json={"slug": "sys-app", "name": "Sys App"}, headers=headers)
    app_id = app.json()["id"]
    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "task", "display_name": "Task"},
        headers=headers,
    )
    entity_data = entity.json()
    sys_field = next(f for f in entity_data["fields"] if f["name"] == "id")

    resp = await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_data['id']}/fields/{sys_field['id']}",
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_relation(client: AsyncClient, builder_user: User) -> None:
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    app = await client.post("/api/v1/apps", json={"slug": "rel-app", "name": "Rel App"}, headers=headers)
    app_id = app.json()["id"]

    customer = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "customer", "display_name": "Customer"},
        headers=headers,
    )
    order = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "order", "display_name": "Order"},
        headers=headers,
    )

    resp = await client.post(
        f"/api/v1/apps/{app_id}/relations",
        json={
            "from_entity_id": customer.json()["id"],
            "to_entity_id": order.json()["id"],
            "relation_type": "one_to_many",
            "from_field_name": "orders",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["relation_type"] == "one_to_many"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_two_relations_to_the_same_entity_pair_under_different_field_names(
    client: AsyncClient, builder_user: User
) -> None:
    """A record legitimately needing two distinct relations to the same
    target entity (e.g. a transfer's "откуда"/"куда", both one_to_many to
    the same Помещение entity) must not be rejected as a duplicate just
    because the entity pair + type matches — only re-creating the exact
    same from_field_name should be."""
    token = await _auth(client, builder_user.email, "Builder1234!")
    headers = {"Authorization": f"Bearer {token}"}

    app = await client.post("/api/v1/apps", json={"slug": "transfer-app", "name": "Transfer App"}, headers=headers)
    app_id = app.json()["id"]
    transfer = await client.post(
        f"/api/v1/apps/{app_id}/entities", json={"slug": "transfer", "display_name": "Transfer"}, headers=headers,
    )
    location = await client.post(
        f"/api/v1/apps/{app_id}/entities", json={"slug": "location", "display_name": "Location"}, headers=headers,
    )
    body = {
        "from_entity_id": transfer.json()["id"], "to_entity_id": location.json()["id"],
        "relation_type": "one_to_many",
    }

    first = await client.post(f"/api/v1/apps/{app_id}/relations",
                               json={**body, "from_field_name": "from_location"}, headers=headers)
    assert first.status_code == 201

    second = await client.post(f"/api/v1/apps/{app_id}/relations",
                                json={**body, "from_field_name": "to_location"}, headers=headers)
    assert second.status_code == 201

    # Re-creating the exact same relation (same field name) is still rejected.
    dup = await client.post(f"/api/v1/apps/{app_id}/relations",
                             json={**body, "from_field_name": "from_location"}, headers=headers)
    assert dup.status_code == 409

    entity_resp = await client.get(f"/api/v1/apps/{app_id}/entities/{transfer.json()['id']}", headers=headers)
    field_names = {f["name"] for f in entity_resp.json()["fields"]}
    assert "from_location" in field_names
    assert "to_location" in field_names
