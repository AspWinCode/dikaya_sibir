"""Authorization matrix for app-level access (ТЗ item 1): platform_admin
must NOT automatically get into an app's editor/runtime/data just by
holding the platform role — only real AppMember (or App.owner_id)
membership grants that. Platform-level screens (user/role management)
are a separate, legitimately platform_admin-gated concern and are not
what this file covers.

Covers, against the real HTTP endpoints (not the service layer directly,
so a regression in any dependency/endpoint wiring is also caught):

- platform_admin with no AppMember row: DENY app/editor/runtime/records
- platform_admin + an explicit AppMember row: ALLOW, per that role
- app owner: ALLOW own app, DENY someone else's app
- app admin (AppMember role="admin"): ALLOW own app, DENY someone else's
- plain member/user (AppMember role="viewer"): ALLOW only the permitted app
- the same deny holds when hitting the route directly by app id (no UI
  layer to hide behind) — entities (editor/schema) and records (runtime)
  endpoints, not just GET /apps/{id}.
"""

import pytest
from app.core.security import hash_password
from app.models.catalog import App, AppMember
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def _make_user(db_session: AsyncSession, email: str, roles: list[str] | None = None) -> User:
    if roles is None:
        roles = []
    for role_id in roles:
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=role_id, is_system=True))
    user = User(email=email, display_name=email, password_hash=hash_password("Passw0rd1!"))
    db_session.add(user)
    await db_session.flush()
    for role_id in roles:
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.flush()
    return user


async def _make_app(db_session: AsyncSession, slug: str, owner: User) -> App:
    app = App(slug=slug, name=slug, owner_id=owner.id)
    db_session.add(app)
    await db_session.flush()
    db_session.add(AppMember(app_id=app.id, user_id=owner.id, role="owner"))
    await db_session.flush()
    return app


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "Passw0rd1!"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
async def owner(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "wh_owner@example.com", roles=["app_builder"])


@pytest.fixture()
async def app_a(db_session: AsyncSession, owner: User) -> App:
    return await _make_app(db_session, "auth-matrix-app-a", owner)


@pytest.fixture()
async def platform_admin_no_membership(db_session: AsyncSession) -> User:
    return await _make_user(db_session, "wh_admin_no_member@example.com", roles=["platform_admin"])


@pytest.mark.asyncio
async def test_platform_admin_without_membership_cannot_open_the_app(
    client: AsyncClient, app_a: App, platform_admin_no_membership: User
) -> None:
    token = await _login(client, platform_admin_no_membership.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_platform_admin_without_membership_cannot_open_editor_schema(
    client: AsyncClient, app_a: App, platform_admin_no_membership: User
) -> None:
    token = await _login(client, platform_admin_no_membership.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}/entities", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_platform_admin_without_membership_does_not_see_the_app_in_list_apps(
    client: AsyncClient, app_a: App, platform_admin_no_membership: User
) -> None:
    token = await _login(client, platform_admin_no_membership.email)
    resp = await client.get("/api/v1/apps", headers=_auth(token))
    assert resp.status_code == 200
    assert str(app_a.id) not in {item["id"] for item in resp.json()["items"]}


@pytest.mark.asyncio
async def test_platform_admin_with_explicit_app_member_can_open_the_app(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    admin = await _make_user(
        db_session, "wh_admin_with_member@example.com", roles=["platform_admin"]
    )
    db_session.add(AppMember(app_id=app_a.id, user_id=admin.id, role="viewer"))
    await db_session.flush()

    token = await _login(client, admin.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_owner_can_open_own_app_but_not_someone_elses(
    client: AsyncClient, db_session: AsyncSession, owner: User, app_a: App
) -> None:
    other_owner = await _make_user(db_session, "wh_other_owner@example.com", roles=["app_builder"])
    app_b = await _make_app(db_session, "auth-matrix-app-b", other_owner)

    token = await _login(client, owner.email)
    own = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert own.status_code == 200

    other = await client.get(f"/api/v1/apps/{app_b.id}", headers=_auth(token))
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_app_admin_member_can_open_own_app_but_not_someone_elses(
    client: AsyncClient, db_session: AsyncSession, owner: User, app_a: App
) -> None:
    app_admin = await _make_user(db_session, "wh_app_admin@example.com")
    db_session.add(AppMember(app_id=app_a.id, user_id=app_admin.id, role="admin"))
    await db_session.flush()
    other_owner = await _make_user(
        db_session, "wh_other_owner_2@example.com", roles=["app_builder"]
    )
    app_b = await _make_app(db_session, "auth-matrix-app-c", other_owner)

    token = await _login(client, app_admin.email)
    own = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert own.status_code == 200
    # app-admin role on app A grants update rights there…
    patch_own = await client.patch(
        f"/api/v1/apps/{app_a.id}",
        json={"description": "updated by app admin"},
        headers=_auth(token),
    )
    assert patch_own.status_code == 200

    other = await client.get(f"/api/v1/apps/{app_b.id}", headers=_auth(token))
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_viewer_member_can_read_own_app_but_cannot_update_it(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    viewer = await _make_user(db_session, "wh_viewer@example.com")
    db_session.add(AppMember(app_id=app_a.id, user_id=viewer.id, role="viewer"))
    await db_session.flush()

    token = await _login(client, viewer.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert resp.status_code == 200

    patch = await client.patch(
        f"/api/v1/apps/{app_a.id}",
        json={"description": "viewer trying to edit"},
        headers=_auth(token),
    )
    assert patch.status_code == 403


@pytest.mark.asyncio
async def test_member_without_any_access_cannot_see_or_open_the_app(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    stranger = await _make_user(db_session, "wh_stranger@example.com", roles=["app_builder"])

    token = await _login(client, stranger.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert resp.status_code == 404

    listing = await client.get("/api/v1/apps", headers=_auth(token))
    assert str(app_a.id) not in {item["id"] for item in listing.json()["items"]}


@pytest.mark.asyncio
async def test_direct_route_access_to_records_is_denied_without_membership(
    client: AsyncClient,
    db_session: AsyncSession,
    owner: User,
    app_a: App,
    platform_admin_no_membership: User,
) -> None:
    """A platform_admin can't bypass the deny by hitting the runtime's own
    record endpoints directly (not just the generic /apps/{id} route)."""
    owner_token = await _login(client, owner.email)
    entity_resp = await client.post(
        f"/api/v1/apps/{app_a.id}/entities",
        json={"slug": "widgets", "display_name": "Widgets"},
        headers=_auth(owner_token),
    )
    assert entity_resp.status_code == 201
    entity_id = entity_resp.json()["id"]

    admin_token = await _login(client, platform_admin_no_membership.email)
    records_resp = await client.get(
        f"/api/v1/apps/{app_a.id}/entities/{entity_id}/records", headers=_auth(admin_token)
    )
    assert records_resp.status_code == 404


# ------------------------------------------------------------------
# publish/check and lock endpoints (ТЗ item 1.1/1.2) — previously had no
# membership check at all beyond the app existing, so any authenticated
# user who knew/guessed the app_id could read publish-validation issues
# or acquire/release someone else's edit lock.
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stranger_cannot_get_publish_check(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    stranger = await _make_user(db_session, "wh_pubcheck_stranger@example.com")
    token = await _login(client, stranger.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}/publish/check", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_platform_admin_without_membership_cannot_get_publish_check(
    client: AsyncClient, app_a: App, platform_admin_no_membership: User
) -> None:
    token = await _login(client, platform_admin_no_membership.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}/publish/check", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_member_can_get_publish_check(client: AsyncClient, owner: User, app_a: App) -> None:
    token = await _login(client, owner.email)
    resp = await client.get(f"/api/v1/apps/{app_a.id}/publish/check", headers=_auth(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stranger_cannot_get_post_or_delete_lock(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    stranger = await _make_user(db_session, "wh_lock_stranger@example.com")
    token = await _login(client, stranger.email)

    # Read access is membership-gated the same way GET /apps/{id} is (404,
    # not 403 — a stranger shouldn't learn the app exists at all).
    get_resp = await client.get(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert get_resp.status_code == 404

    # Acquire/release go through the same owner/admin/editor role check as
    # every other write endpoint in this file (e.g. PATCH /apps/{id}), which
    # already answers "wrong role" with 403 once the app's existence is
    # established — consistent with that existing convention here too.
    post_resp = await client.post(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert post_resp.status_code == 403

    delete_resp = await client.delete(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert delete_resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_acquire_edit_lock(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    viewer = await _make_user(db_session, "wh_lock_viewer@example.com")
    db_session.add(AppMember(app_id=app_a.id, user_id=viewer.id, role="viewer"))
    await db_session.flush()

    token = await _login(client, viewer.email)
    get_resp = await client.get(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert get_resp.status_code == 200  # read access only

    post_resp = await client.post(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert post_resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_member_can_acquire_and_release_edit_lock(
    client: AsyncClient, db_session: AsyncSession, app_a: App
) -> None:
    admin = await _make_user(db_session, "wh_lock_admin@example.com")
    db_session.add(AppMember(app_id=app_a.id, user_id=admin.id, role="admin"))
    await db_session.flush()

    token = await _login(client, admin.email)
    post_resp = await client.post(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert post_resp.status_code == 204

    delete_resp = await client.delete(f"/api/v1/apps/{app_a.id}/lock", headers=_auth(token))
    assert delete_resp.status_code == 204


# ------------------------------------------------------------------
# list_apps org-scoping (ТЗ item 1.3) — belonging to the same org as an
# app must NOT be enough to see it; only ownership/AppMember should.
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_member_without_app_membership_does_not_see_the_app_in_list_apps(
    client: AsyncClient, db_session: AsyncSession, owner: User, app_a: App
) -> None:
    from app.models.identity import Organisation

    org = Organisation(slug="wh-org-scoping-test", display_name="Org Scoping Test")
    db_session.add(org)
    await db_session.flush()

    owner.org_id = org.id
    app_a.org_id = org.id
    org_colleague = await _make_user(db_session, "wh_org_colleague@example.com")
    org_colleague.org_id = org.id
    await db_session.flush()

    token = await _login(client, org_colleague.email)
    listing = await client.get("/api/v1/apps", headers=_auth(token))
    assert listing.status_code == 200
    assert str(app_a.id) not in {item["id"] for item in listing.json()["items"]}

    direct = await client.get(f"/api/v1/apps/{app_a.id}", headers=_auth(token))
    assert direct.status_code == 404
