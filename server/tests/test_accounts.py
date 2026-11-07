import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import get_session, make_engine
from app.main import app
from app.services import auth_service


def exercise(tmp_path: Path, monkeypatch, scenario) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / f"accounts-{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")

    async def run() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def session_override():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await scenario(client)
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(run())
    get_settings.cache_clear()


async def register(client: AsyncClient, username: str = "demo", password: str = "secret123"):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "confirm_password": password},
    )


def test_register_signs_in_and_me_reads_session(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        created = await register(client)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["username"] == "demo"
        assert "ledgercrew_session" in created.cookies

        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json() == body

    exercise(tmp_path, monkeypatch, scenario)


def test_register_rejects_duplicates_case_insensitively(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await register(client, "Demo")).status_code == 201
        duplicate = await register(client, "demo")
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "username_taken"

    exercise(tmp_path, monkeypatch, scenario)


def test_login_and_logout_rotate_the_session(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await register(client)).status_code == 201
        wrong = await client.post("/api/v1/auth/login", json={"username": "demo", "password": "nope"})
        assert wrong.status_code == 401

        original = client.cookies.get("ledgercrew_session")
        logged_in = await client.post("/api/v1/auth/login", json={"username": "DEMO", "password": "secret123"})
        assert logged_in.status_code == 200
        assert client.cookies.get("ledgercrew_session") != original
        assert (await client.get("/api/v1/auth/me")).status_code == 200

        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    exercise(tmp_path, monkeypatch, scenario)


def test_trial_creates_one_free_order_idempotently(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await client.post("/api/v1/auth/trial", json={"request_id": "missing-session"})).status_code == 401
        assert (await register(client)).status_code == 201

        first = await client.post("/api/v1/auth/trial", json={"request_id": "trial-request-1"})
        assert first.status_code == 201, first.text
        payload = first.json()
        assert payload["plan_id"] == "FREE"
        assert payload["amount_cents"] == 0
        assert payload["payment_status"] == "not_required"

        replay = await client.post("/api/v1/auth/trial", json={"request_id": "trial-request-1"})
        assert replay.status_code == 201
        assert replay.json()["order_no"] == payload["order_no"]

        studios = (await client.get("/api/v1/studios")).json()
        assert len(studios) == 1
        orders = (await client.get("/api/v1/orders")).json()
        assert [order["order_no"] for order in orders] == [payload["order_no"]]
        assert orders[0]["price_cents"] == 0
        assert orders[0]["status"] == "draft"

    exercise(tmp_path, monkeypatch, scenario)


def test_admin_role_controls_owner_console(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await register(client, "shop-owner")).status_code == 201
        customer = await client.get("/api/v1/auth/me")
        assert customer.json()["role"] == "customer"
        assert (await client.get("/api/v1/owner/dashboard")).status_code == 403

        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        assert (await register(client, "owner")).status_code == 201
        admin = await client.get("/api/v1/auth/me")
        assert admin.json()["role"] == "owner"
        assert (await client.get("/api/v1/owner/dashboard")).status_code == 200

    exercise(tmp_path, monkeypatch, scenario)


def test_cookie_session_reaches_customer_flow(tmp_path: Path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await register(client, "studio-owner")).status_code == 201
        intake = await client.post("/api/v1/intakes", json={})
        assert intake.status_code == 201, intake.text
        assert intake.json()["status"] == "collecting"

    exercise(tmp_path, monkeypatch, scenario)


def test_admin_bootstrap_creates_account_and_resyncs_password(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / f"admin-{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")

    async def run() -> None:
        engine = make_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as session:
                created = await auth_service.ensure_admin(session, "owner", "first-pass-1")
                assert (created.username, created.username_key) == ("owner", "owner")
            async with sessions() as session:
                assert await auth_service.login(session, "owner", "first-pass-1") is not None
                await auth_service.ensure_admin(session, "owner", "second-pass-2")
            async with sessions() as session:
                with pytest.raises(AppError):
                    await auth_service.login(session, "owner", "first-pass-1")
                assert await auth_service.login(session, "owner", "second-pass-2") is not None
        finally:
            await engine.dispose()

    asyncio.run(run())
    get_settings.cache_clear()
