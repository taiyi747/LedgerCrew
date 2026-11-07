import asyncio

from httpx import ASGITransport, AsyncClient
from test_stage2 import create_order, exercise

from app.core.config import get_settings
from app.core.limits import SSEConnectionLimiter
from app.main import app


def test_api_rate_limit_returns_429(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("API_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("API_RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    async def check() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            limited = await client.get("/api/v1/auth/me")
            assert limited.status_code == 429
            assert limited.json()["error"]["code"] == "rate_limited"

    asyncio.run(check())
    get_settings.cache_clear()


def test_sse_connection_limit_and_release() -> None:
    async def check() -> None:
        limiter = SSEConnectionLimiter()
        assert await limiter.acquire(1)
        assert not await limiter.acquire(1)
        assert limiter.active == 1
        await limiter.release()
        assert limiter.active == 0
        assert await limiter.acquire(1)
        await limiter.release()

    asyncio.run(check())


def test_sse_request_releases_slot_after_one_shot(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        response = await client.get(f"/api/v1/orders/{order_id}/events/stream?follow=false",
                                    headers={"X-User-Id": "alice"})
        assert response.status_code == 200
        assert app.state.sse_connection_limiter.active == 0

    exercise(tmp_path, monkeypatch, scenario, sse_max_connections=1)
