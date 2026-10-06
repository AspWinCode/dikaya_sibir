"""Record CRUD + filter engine integration tests."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Role, User, UserRole


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="rec_builder@example.com",
        display_name="Builder",
        password_hash=hash_password("Build1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _setup_entity(client: AsyncClient, token: str) -> tuple[str, str]:
    """Create an app + entity, return (app_id, entity_id)."""
    import uuid
    slug = f"rec-app-{uuid.uuid4().hex[:6]}"
    app = await client.post(
        "/api/v1/apps", json={"slug": slug, "name": "Record Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    app_id = app.json()["id"]

    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "invoice", "display_name": "Invoice"},
        headers={"Authorization": f"Bearer {token}"},
    )
    entity_id = entity.json()["id"]

    # Add a couple of custom fields
    for field in [
        {"name": "title", "display_name": "Title", "field_type": "text", "is_required": True},
        {"name": "amount", "display_name": "Amount", "field_type": "decimal"},
        {"name": "status", "display_name": "Status", "field_type": "select",
         "field_options": {"choices": [{"value": "draft"}, {"value": "paid"}]}},
    ]:
        await client.post(
            f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
            json=field,
            headers={"Authorization": f"Bearer {token}"},
        )

    return app_id, entity_id


# ------------------------------------------------------------------
# Record CRUD
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_get_record(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Invoice #1", "amount": 100.0, "status": "draft"}},
        headers=headers,
    )
    assert resp.status_code == 201
    rec = resp.json()
    assert rec["payload"]["title"] == "Invoice #1"
    assert rec["version"] == 1

    # GET
    get_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec['id']}",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == rec["id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_select_field_with_string_choices(client: AsyncClient, builder: User) -> None:
    """Fields created via the entity builder store `choices` as bare strings
    (not `{value, label}` objects — see test_create_and_get_record's fixture
    for that shape). Saving a value for such a field must not crash."""
    token = await _login(client, builder.email, "Build1234!")
    headers = {"Authorization": f"Bearer {token}"}

    import uuid
    slug = f"rec-app-{uuid.uuid4().hex[:6]}"
    app = await client.post(
        "/api/v1/apps", json={"slug": slug, "name": "String Choices App"}, headers=headers,
    )
    app_id = app.json()["id"]
    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "employee", "display_name": "Employee"},
        headers=headers,
    )
    entity_id = entity.json()["id"]
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={
            "name": "position", "display_name": "Position", "field_type": "select",
            "field_options": {"choices": ["Мастер", "Стажёр"]},
        },
        headers=headers,
    )

    ok = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"position": "Мастер"}},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["payload"]["position"] == "Мастер"

    bad = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"position": "Директор"}},
        headers=headers,
    )
    assert bad.status_code == 422, bad.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_record_increments_version(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Old title"}},
        headers=headers,
    )
    rec_id = create.json()["id"]

    update = await client.patch(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}",
        json={"payload": {"title": "New title", "amount": 200.0}},
        headers=headers,
    )
    assert update.status_code == 200
    assert update.json()["version"] == 2
    assert update.json()["payload"]["title"] == "New title"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_soft_delete_hides_record(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "To delete"}},
        headers=headers,
    )
    rec_id = create.json()["id"]

    # Soft delete
    del_resp = await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Should 404 on GET
    get_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}",
        headers=headers,
    )
    assert get_resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_restore_deleted_record(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Restorable"}},
        headers=headers,
    )
    rec_id = create.json()["id"]
    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}", headers=headers
    )

    restore = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}/restore",
        headers=headers,
    )
    assert restore.status_code == 200


# ------------------------------------------------------------------
# Soft-delete audit fields + recycle bin (ТЗ 3.9.1 / Приложение B)
# ------------------------------------------------------------------

@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    for role_id in ("app_builder", "platform_admin"):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=role_id, is_system=True))
    user = User(
        email="rec_admin@example.com",
        display_name="Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    for role_id in ("app_builder", "platform_admin"):
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.flush()
    return user


async def _get_record_via_list(
    client: AsyncClient, app_id: str, entity_id: str, record_id: str, headers: dict,
) -> dict:
    """The GET /{record_id} endpoint 404s on soft-deleted records; fetch it
    through the include_deleted list instead to inspect deleted_at/deleted_by."""
    resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records?include_deleted=true&limit=200",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    match = next(r for r in resp.json()["items"] if r["id"] == record_id)
    return match


@pytest.mark.integration
@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at_and_deleted_by(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Track deletion metadata"}},
        headers=headers,
    )
    rec_id = create.json()["id"]

    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}", headers=headers,
    )

    record = await _get_record_via_list(client, app_id, entity_id, rec_id, headers)
    assert record["is_deleted"] is True
    assert record["deleted_at"] is not None
    assert record["deleted_by"] == str(admin.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_restore_clears_deleted_at_and_deleted_by(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Restore clears metadata"}},
        headers=headers,
    )
    rec_id = create.json()["id"]
    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}", headers=headers,
    )
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}/restore", headers=headers,
    )

    record = await _get_record_via_list(client, app_id, entity_id, rec_id, headers)
    assert record["is_deleted"] is False
    assert record["deleted_at"] is None
    assert record["deleted_by"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recycle_bin_requires_auth(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, _ = await _setup_entity(client, token)
    resp = await client.get(f"/api/v1/apps/{app_id}/recycle-bin")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recycle_bin_forbidden_for_non_admin(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, _ = await _setup_entity(client, token)
    resp = await client.get(
        f"/api/v1/apps/{app_id}/recycle-bin",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recycle_bin_lists_deleted_record(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "In the bin"}},
        headers=headers,
    )
    rec_id = create.json()["id"]
    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}", headers=headers,
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/recycle-bin", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == rec_id
    assert items[0]["entity_id"] == entity_id
    assert items[0]["entity_slug"] == "invoice"
    assert items[0]["is_cascade_deleted"] is False
    assert items[0]["deleted_by"] == str(admin.id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recycle_bin_excludes_active_and_restored_records(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    active = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Still active"}}, headers=headers,
    )
    deleted_then_restored = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Deleted then restored"}}, headers=headers,
    )
    restored_id = deleted_then_restored.json()["id"]
    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{restored_id}", headers=headers,
    )
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{restored_id}/restore", headers=headers,
    )

    resp = await client.get(f"/api/v1/apps/{app_id}/recycle-bin", headers=headers)
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert active.json()["id"] not in ids
    assert restored_id not in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recycle_bin_filters_by_entity(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    other_entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "other", "display_name": "Other"},
        headers=headers,
    )
    other_entity_id = other_entity.json()["id"]

    rec1 = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "In invoice"}}, headers=headers,
    )
    rec2 = await client.post(
        f"/api/v1/apps/{app_id}/entities/{other_entity_id}/records",
        json={"payload": {}}, headers=headers,
    )
    for eid, rid in [(entity_id, rec1.json()["id"]), (other_entity_id, rec2.json()["id"])]:
        await client.delete(f"/api/v1/apps/{app_id}/entities/{eid}/records/{rid}", headers=headers)

    resp = await client.get(
        f"/api/v1/apps/{app_id}/recycle-bin?entity_id={entity_id}", headers=headers,
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["entity_id"] == entity_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascade_delete_marks_child_as_cascade_deleted(client: AsyncClient, admin: User) -> None:
    """Deleting a parent soft-deletes one_to_many children and stamps
    deleted_at/deleted_by/cascade_deleted_by on them too."""
    token = await _login(client, admin.email, "Admin1234!")
    headers = {"Authorization": f"Bearer {token}"}
    app_id, parent_entity_id = await _setup_entity(client, token)

    child_entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "line_item", "display_name": "Line Item"},
        headers=headers,
    )
    child_entity_id = child_entity.json()["id"]
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{child_entity_id}/fields",
        json={"name": "invoice_id", "display_name": "Invoice", "field_type": "text"},
        headers=headers,
    )

    await client.post(
        f"/api/v1/apps/{app_id}/relations",
        json={
            "from_entity_id": child_entity_id,
            "to_entity_id": parent_entity_id,
            "relation_type": "one_to_many",
            "from_field_name": "invoice_id",
        },
        headers=headers,
    )

    parent = await client.post(
        f"/api/v1/apps/{app_id}/entities/{parent_entity_id}/records",
        json={"payload": {"title": "Parent invoice"}}, headers=headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        f"/api/v1/apps/{app_id}/entities/{child_entity_id}/records",
        json={"payload": {"invoice_id": parent_id}}, headers=headers,
    )
    child_id = child.json()["id"]

    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{parent_entity_id}/records/{parent_id}", headers=headers,
    )

    child_row = await _get_record_via_list(client, app_id, child_entity_id, child_id, headers)
    assert child_row["is_deleted"] is True
    assert child_row["deleted_at"] is not None
    assert child_row["deleted_by"] == str(admin.id)  # the actor who deleted the parent

    bin_resp = await client.get(f"/api/v1/apps/{app_id}/recycle-bin", headers=headers)
    bin_by_id = {item["id"]: item for item in bin_resp.json()["items"]}
    assert bin_by_id[child_id]["is_cascade_deleted"] is True
    assert bin_by_id[parent_id]["is_cascade_deleted"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascade_restore_clears_child_deleted_fields(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    headers = {"Authorization": f"Bearer {token}"}
    app_id, parent_entity_id = await _setup_entity(client, token)

    child_entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "line_item2", "display_name": "Line Item 2"},
        headers=headers,
    )
    child_entity_id = child_entity.json()["id"]
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{child_entity_id}/fields",
        json={"name": "invoice_id", "display_name": "Invoice", "field_type": "text"},
        headers=headers,
    )
    await client.post(
        f"/api/v1/apps/{app_id}/relations",
        json={
            "from_entity_id": child_entity_id,
            "to_entity_id": parent_entity_id,
            "relation_type": "one_to_many",
            "from_field_name": "invoice_id",
        },
        headers=headers,
    )

    parent = await client.post(
        f"/api/v1/apps/{app_id}/entities/{parent_entity_id}/records",
        json={"payload": {"title": "Parent"}}, headers=headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        f"/api/v1/apps/{app_id}/entities/{child_entity_id}/records",
        json={"payload": {"invoice_id": parent_id}}, headers=headers,
    )
    child_id = child.json()["id"]

    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{parent_entity_id}/records/{parent_id}", headers=headers,
    )
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{parent_entity_id}/records/{parent_id}/restore", headers=headers,
    )

    child_row = await _get_record_via_list(client, app_id, child_entity_id, child_id, headers)
    assert child_row["is_deleted"] is False
    assert child_row["deleted_at"] is None
    assert child_row["deleted_by"] is None


# ------------------------------------------------------------------
# Filter engine
# ------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_filter_eq(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/entities/{entity_id}/records"

    for title in ("Alpha", "Beta", "Gamma"):
        await client.post(base, json={"payload": {"title": title}}, headers=headers)

    resp = await client.get(f"{base}?filter=title:eq:Alpha", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["payload"]["title"] == "Alpha"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filter_icontains(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/entities/{entity_id}/records"

    for title in ("Invoice 001", "Invoice 002", "Receipt 001"):
        await client.post(base, json={"payload": {"title": title}}, headers=headers)

    resp = await client.get(f"{base}?filter=title:icontains:invoice", headers=headers)
    items = resp.json()["items"]
    assert len(items) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filter_gte_numeric(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/entities/{entity_id}/records"

    for amount in (10, 50, 100, 200):
        await client.post(
            base,
            json={"payload": {"title": f"Inv {amount}", "amount": amount}},
            headers=headers,
        )

    resp = await client.get(f"{base}?filter=amount:gte:100", headers=headers)
    items = resp.json()["items"]
    amounts = [i["payload"]["amount"] for i in items]
    assert all(float(a) >= 100 for a in amounts)
    assert len(items) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_required_field_validation(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    # 'title' is required; omitting it should fail
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"amount": 99}},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_currency_field_rejects_non_numeric_value(client: AsyncClient, builder: User) -> None:
    """A `currency` field used to fall through validation with no type check
    at all (only "number"/"decimal" were validated) — a non-numeric value
    must be rejected just like for "decimal"."""
    token = await _login(client, builder.email, "Build1234!")
    headers = {"Authorization": f"Bearer {token}"}

    import uuid
    slug = f"rec-app-{uuid.uuid4().hex[:6]}"
    app = await client.post("/api/v1/apps", json={"slug": slug, "name": "Currency App"}, headers=headers)
    app_id = app.json()["id"]
    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities", json={"slug": "op", "display_name": "Operation"}, headers=headers,
    )
    entity_id = entity.json()["id"]
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "cost", "display_name": "Cost", "field_type": "currency"},
        headers=headers,
    )

    bad = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"cost": "not-a-number"}},
        headers=headers,
    )
    assert bad.status_code == 422

    good = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"cost": 1500.50}},
        headers=headers,
    )
    assert good.status_code == 201
    assert good.json()["payload"]["cost"] == 1500.50


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_field_validation(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Ok", "nonexistent_field": "x"}},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cursor_pagination(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/entities/{entity_id}/records"

    for i in range(7):
        await client.post(base, json={"payload": {"title": f"Record {i}"}}, headers=headers)

    page1 = await client.get(f"{base}?limit=4", headers=headers)
    assert page1.json()["has_more"] is True
    cursor = page1.json()["next_cursor"]

    page2 = await client.get(f"{base}?limit=4&cursor={cursor}", headers=headers)
    assert page2.status_code == 200
    assert len(page2.json()["items"]) == 3
    assert page2.json()["has_more"] is False
