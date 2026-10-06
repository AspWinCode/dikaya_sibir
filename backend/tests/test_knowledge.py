"""Knowledge base tests (ТЗ 3.12): article CRUD/search + image hosting."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.knowledge import KnowledgeService

from tests.test_files import FakeAntivirus, FakeStorage

pytestmark = pytest.mark.integration


@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "platform_admin"):
        db_session.add(Role(id="platform_admin", display_name="Platform Admin", is_system=True))
    user = User(
        email="kb_admin@example.com", display_name="KB Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    await db_session.flush()
    return user


@pytest.fixture()
async def regular_user(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="Builder", is_system=True))
    user = User(
        email="kb_user@example.com", display_name="Regular",
        password_hash=hash_password("User1234!"),
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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------
# Article CRUD
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_articles_empty(client: AsyncClient, regular_user: User) -> None:
    token = await _login(client, regular_user.email, "User1234!")
    resp = await client.get("/api/v1/kb/articles", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_article_forbidden_for_non_admin(client: AsyncClient, regular_user: User) -> None:
    token = await _login(client, regular_user.email, "User1234!")
    resp = await client.post(
        "/api/v1/kb/articles",
        json={"title": "How to create a rule", "content": "<p>Steps...</p>"},
        headers=_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_article_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/kb/articles", json={"title": "X", "content": ""})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_create_article_with_auto_slug(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    resp = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Как создать правило", "category": "Правила", "content": "<p>Шаг 1...</p>"},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # Cyrillic title has no a-z0-9 chars to keep, so slugify() falls back to
    # "article" + a random suffix rather than an empty/all-dash slug.
    assert data["slug"].startswith("article-")
    assert data["is_published"] is True


@pytest.mark.asyncio
async def test_admin_can_set_explicit_slug(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    resp = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Rules", "slug": "how-to-create-a-rule", "content": "<p>Steps</p>"},
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] == "how-to-create-a-rule"


@pytest.mark.asyncio
async def test_duplicate_slug_returns_409(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    body = {"title": "First", "slug": "dup-slug", "content": ""}
    r1 = await client.post("/api/v1/kb/articles", json=body, headers=_headers(token))
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        "/api/v1/kb/articles", json={**body, "title": "Second"}, headers=_headers(token),
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_article_by_slug_and_by_id(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    create = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Lookup fields", "slug": "lookup-fields", "content": "<p>...</p>"},
        headers=_headers(token),
    )
    article = create.json()

    by_slug = await client.get(f"/api/v1/kb/articles/{article['slug']}", headers=_headers(token))
    assert by_slug.status_code == 200
    assert by_slug.json()["id"] == article["id"]

    by_id = await client.get(f"/api/v1/kb/articles/{article['id']}", headers=_headers(token))
    assert by_id.status_code == 200
    assert by_id.json()["slug"] == article["slug"]


@pytest.mark.asyncio
async def test_get_unknown_article_404(client: AsyncClient, regular_user: User) -> None:
    token = await _login(client, regular_user.email, "User1234!")
    resp = await client.get("/api/v1/kb/articles/does-not-exist", headers=_headers(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unpublished_article_hidden_from_regular_user(
    client: AsyncClient, admin: User, regular_user: User,
) -> None:
    admin_token = await _login(client, admin.email, "Admin1234!")
    create = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Draft", "slug": "draft-article", "content": "", "is_published": False},
        headers=_headers(admin_token),
    )
    assert create.status_code == 201

    user_token = await _login(client, regular_user.email, "User1234!")
    resp = await client.get("/api/v1/kb/articles/draft-article", headers=_headers(user_token))
    assert resp.status_code == 404

    admin_resp = await client.get("/api/v1/kb/articles/draft-article", headers=_headers(admin_token))
    assert admin_resp.status_code == 200


@pytest.mark.asyncio
async def test_unpublished_article_excluded_from_regular_user_list(
    client: AsyncClient, admin: User, regular_user: User,
) -> None:
    admin_token = await _login(client, admin.email, "Admin1234!")
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "Hidden", "slug": "hidden-article", "content": "", "is_published": False},
        headers=_headers(admin_token),
    )

    user_token = await _login(client, regular_user.email, "User1234!")
    resp = await client.get("/api/v1/kb/articles", headers=_headers(user_token))
    slugs = [a["slug"] for a in resp.json()]
    assert "hidden-article" not in slugs

    admin_list = await client.get("/api/v1/kb/articles", headers=_headers(admin_token))
    admin_slugs = [a["slug"] for a in admin_list.json()]
    assert "hidden-article" in admin_slugs


@pytest.mark.asyncio
async def test_update_article(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    create = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Old title", "slug": "update-me", "content": "old"},
        headers=_headers(token),
    )
    article_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/kb/articles/{article_id}",
        json={"title": "New title", "content": "new"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "New title"
    assert resp.json()["content"] == "new"


@pytest.mark.asyncio
async def test_update_unknown_article_404(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    resp = await client.patch(
        f"/api/v1/kb/articles/{uuid.uuid4()}", json={"title": "X"}, headers=_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_article(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    create = await client.post(
        "/api/v1/kb/articles",
        json={"title": "To delete", "slug": "delete-me", "content": ""},
        headers=_headers(token),
    )
    article_id = create.json()["id"]

    resp = await client.delete(f"/api/v1/kb/articles/{article_id}", headers=_headers(token))
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/v1/kb/articles/{article_id}", headers=_headers(token))
    assert get_resp.status_code == 404


# ------------------------------------------------------------------
# Search / categories
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_matches_title_and_content(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "Настройка формул", "slug": "formulas", "content": "Формулы вычисляются автоматически"},
        headers=_headers(token),
    )
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "Импорт данных", "slug": "import-data", "content": "Загрузите CSV файл"},
        headers=_headers(token),
    )

    by_title = await client.get("/api/v1/kb/articles?q=формул", headers=_headers(token))
    assert {a["slug"] for a in by_title.json()} == {"formulas"}

    by_content = await client.get("/api/v1/kb/articles?q=CSV", headers=_headers(token))
    assert {a["slug"] for a in by_content.json()} == {"import-data"}


@pytest.mark.asyncio
async def test_filter_by_category(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "A", "slug": "cat-a", "category": "Правила", "content": ""},
        headers=_headers(token),
    )
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "B", "slug": "cat-b", "category": "Импорт", "content": ""},
        headers=_headers(token),
    )

    resp = await client.get("/api/v1/kb/articles?category=Правила", headers=_headers(token))
    assert {a["slug"] for a in resp.json()} == {"cat-a"}


@pytest.mark.asyncio
async def test_articles_are_ordered_by_display_order(client: AsyncClient, admin: User) -> None:
    """Admin-controlled ordering (used by the Learning page's steps/materials
    sections) — created out of order, must come back sorted by display_order."""
    token = await _login(client, admin.email, "Admin1234!")
    for title, slug, order in [("Third", "step-third", 2), ("First", "step-first", 0), ("Second", "step-second", 1)]:
        await client.post(
            "/api/v1/kb/articles",
            json={"title": title, "slug": slug, "category": "Следующие шаги", "display_order": order, "content": ""},
            headers=_headers(token),
        )

    resp = await client.get("/api/v1/kb/articles?category=Следующие шаги", headers=_headers(token))
    assert resp.status_code == 200
    assert [a["slug"] for a in resp.json()] == ["step-first", "step-second", "step-third"]


@pytest.mark.asyncio
async def test_admin_can_reorder_article(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    created = await client.post(
        "/api/v1/kb/articles",
        json={"title": "Step", "slug": "reorder-me", "category": "Следующие шаги", "content": ""},
        headers=_headers(token),
    )
    assert created.json()["display_order"] == 0

    updated = await client.patch(
        "/api/v1/kb/articles/reorder-me",
        json={"display_order": 5},
        headers=_headers(token),
    )
    assert updated.status_code == 200
    assert updated.json()["display_order"] == 5

    # Survives a fresh read, not just the mutation response.
    fetched = await client.get("/api/v1/kb/articles/reorder-me", headers=_headers(token))
    assert fetched.json()["display_order"] == 5


@pytest.mark.asyncio
async def test_list_categories_returns_distinct_published_categories(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    for slug, category, published in [
        ("c1", "Правила", True), ("c2", "Правила", True),
        ("c3", "Импорт", True), ("c4", "Черновик", False),
    ]:
        await client.post(
            "/api/v1/kb/articles",
            json={"title": slug, "slug": slug, "category": category, "content": "", "is_published": published},
            headers=_headers(token),
        )

    resp = await client.get("/api/v1/kb/categories", headers=_headers(token))
    assert resp.json() == ["Импорт", "Правила"]


@pytest.mark.asyncio
async def test_excerpt_strips_html_and_truncates(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    long_text = "слово " * 100
    await client.post(
        "/api/v1/kb/articles",
        json={"title": "Long", "slug": "long-article", "content": f"<p><b>{long_text}</b></p>"},
        headers=_headers(token),
    )

    resp = await client.get("/api/v1/kb/articles", headers=_headers(token))
    item = next(a for a in resp.json() if a["slug"] == "long-article")
    assert "<" not in item["excerpt"]
    assert len(item["excerpt"]) <= 201  # 200 chars + ellipsis


# ------------------------------------------------------------------
# Images — unit-level via KnowledgeService with fakes (no real S3/ClamAV)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_image_success(db_session: AsyncSession) -> None:
    svc = KnowledgeService(db_session)
    storage = FakeStorage()
    av = FakeAntivirus()

    result = await svc.upload_image(b"fake-png-bytes", "image/png", storage, av, actor_id=None)
    assert result.url == f"/api/v1/kb/images/{result.id}/file"
    assert any(k.startswith("kb/") for k in storage.objects)


@pytest.mark.asyncio
async def test_upload_image_rejects_bad_content_type() -> None:
    # Raises before any DB access, so — like the import size-limit tests —
    # no real session is needed.
    from app.services.knowledge import ImageError
    svc = KnowledgeService(None)  # type: ignore[arg-type]
    with pytest.raises(ImageError, match="Unsupported image type"):
        await svc.upload_image(b"data", "application/pdf", FakeStorage(), FakeAntivirus(), actor_id=None)


@pytest.mark.asyncio
async def test_upload_image_rejects_infected_file() -> None:
    from app.services.knowledge import ImageError
    svc = KnowledgeService(None)  # type: ignore[arg-type]
    with pytest.raises(ImageError, match="antivirus"):
        await svc.upload_image(
            b"eicar", "image/png", FakeStorage(), FakeAntivirus(infected=True), actor_id=None,
        )


@pytest.mark.asyncio
async def test_upload_image_rejects_oversized(monkeypatch) -> None:
    from app.services.knowledge import ImageError
    svc = KnowledgeService(None)  # type: ignore[arg-type]
    monkeypatch.setattr(svc, "_MAX_IMAGE_SIZE", 10)
    with pytest.raises(ImageError, match="exceeds the maximum size"):
        await svc.upload_image(b"x" * 100, "image/png", FakeStorage(), FakeAntivirus(), actor_id=None)


@pytest.mark.asyncio
async def test_get_image_url_unknown_id_raises(db_session: AsyncSession) -> None:
    from app.services.knowledge import ImageNotFoundError
    svc = KnowledgeService(db_session)
    with pytest.raises(ImageNotFoundError):
        await svc.get_image_url(uuid.uuid4(), FakeStorage())


# ------------------------------------------------------------------
# Images — HTTP layer (upload requires admin; file redirect is public)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_upload_endpoint_forbidden_for_non_admin(client: AsyncClient, regular_user: User) -> None:
    import io
    token = await _login(client, regular_user.email, "User1234!")
    resp = await client.post(
        "/api/v1/kb/images",
        headers=_headers(token),
        files={"file": ("pic.png", io.BytesIO(b"data"), "image/png")},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_image_file_endpoint_404_for_unknown_id(client: AsyncClient) -> None:
    # No Authorization header at all — this route is deliberately public.
    resp = await client.get(f"/api/v1/kb/images/{uuid.uuid4()}/file", follow_redirects=False)
    assert resp.status_code == 404
