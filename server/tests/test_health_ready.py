import asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_auth import serve

from app.core.config import get_settings
from app.db.session import get_session, make_engine
from app.main import app


def test_liveness_and_readiness_report_unverified_worker(tmp_path, monkeypatch) -> None:
    async def scenario(client: AsyncClient) -> None:
        assert (await client.get("/health/live")).json() == {"status": "ok"}
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["components"]["database"] == "ok"
        assert response.json()["components"]["worker"] == {"status": "unavailable", "active_count": 0}
        assert response.json()["components"]["workflow"] == "configured"
        assert response.json()["components"]["task_queue"] == {
            "status": "ok", "queued": 0, "running": 0, "retrying": 0,
            "failed": 0, "timeout": 0, "cancelled": 0}

    serve(tmp_path, monkeypatch, scenario, db=True)


def test_readiness_reports_database_failure_without_secret(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'missing.db').as_posix()}")
    get_settings.cache_clear()
    engine = make_engine(get_settings().database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with sessions() as session:
            yield session

    async def run() -> None:
        app.dependency_overrides[get_session] = session_override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/health/ready")
                assert response.status_code == 503
                assert response.json()["components"]["database"] == "unavailable"
                assert "sqlite" not in response.text.lower()
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(run())
