import asyncio
import hashlib
import io
import stat
import zipfile
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.db.session import get_session, make_engine
from app.main import app
from app.storage.local import LocalStorage, get_storage


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "red").save(output, format="PNG")
    return output.getvalue()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


def exercise(tmp_path: Path, monkeypatch, scenario, **limits) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / f"stage2-{uuid4().hex}.db"
    storage_path = tmp_path / "storage"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_path))
    for key, value in limits.items():
        monkeypatch.setenv(key.upper(), str(value))
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
        app.dependency_overrides[get_storage] = lambda: LocalStorage(str(storage_path))
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await scenario(client, storage_path)
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()

    asyncio.run(run())
    get_settings.cache_clear()


async def create_order(client: AsyncClient, user: str = "alice") -> tuple[str, str]:
    headers = {"X-User-Id": user}
    studio = await client.post("/api/v1/studios", json={"name": "Studio", "business_type": "digital_services"}, headers=headers)
    assert studio.status_code == 201, studio.text
    studio_id = studio.json()["id"]
    order = await client.post("/api/v1/orders", json={"studio_id": studio_id, "period_start": "2026-10-01", "period_end": "2026-10-31", "service_scope": "monthly_records"}, headers=headers)
    assert order.status_code == 201, order.text
    assert order.json()["status"] == "draft"
    assert order.json()["is_simulated"] is True
    return studio_id, order.json()["id"]


def test_studio_order_access_and_validation(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        studio_id, order_id = await create_order(client)
        alice = {"X-User-Id": "alice"}
        bob = {"X-User-Id": "bob"}
        assert len((await client.get("/api/v1/studios", headers=alice)).json()) == 1
        assert (await client.get(f"/api/v1/studios/{studio_id}", headers=bob)).status_code == 404
        assert (await client.get("/api/v1/orders", headers=bob)).json() == []
        assert (await client.get(f"/api/v1/orders/{order_id}", headers=bob)).status_code == 404
        assert (await client.get("/api/v1/orders", headers=alice)).json()[0]["order_no"].startswith("LC-")
        assert (await client.post("/api/v1/orders", json={"studio_id": studio_id, "period_start": "2026-11-02", "period_end": "2026-11-01", "service_scope": "monthly_records"}, headers=alice)).status_code == 422
        assert (await client.get("/api/v1/orders")).status_code == 401
    exercise(tmp_path, monkeypatch, scenario)


def test_image_csv_multi_upload_hash_and_permission(tmp_path, monkeypatch) -> None:
    async def scenario(client, storage):
        _, order_id = await create_order(client)
        image = png_bytes()
        csv_data = b"transaction_id,date,counterparty,amount,direction,remark\n1,2026-10-01,A,1.00,in,x\n"
        alice = {"X-User-Id": "alice"}
        bob = {"X-User-Id": "bob"}
        image_result = await client.post(f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"}, files=[("files", ("invoice.png", image, "image/png"))], headers=alice)
        assert image_result.status_code == 201, image_result.text
        record = image_result.json()["files"][0]
        assert record["validation_status"] == "valid"
        assert record["sha256"] == hashlib.sha256(image).hexdigest()
        assert "storage_key" not in record
        assert (await client.get(f"/api/v1/files/{record['id']}/download", headers=alice)).content == image
        assert (await client.get(f"/api/v1/files/{record['id']}/download", headers=bob)).status_code == 404
        assert (await client.get(f"/api/v1/files/{record['id']}", headers=bob)).status_code == 404
        csv_result = await client.post(f"/api/v1/orders/{order_id}/files", data={"file_category": "bank_statement_csv"}, files=[("files", ("bank.csv", csv_data, "text/csv"))], headers=alice)
        assert csv_result.status_code == 201, csv_result.text
        assert csv_result.json()["files"][0]["mime_type"] == "text/csv"
        multi = await client.post(f"/api/v1/orders/{order_id}/files", data={"file_category": "supporting_material"}, files=[("files", ("a.png", image, "image/png")), ("files", ("b.png", image, "image/png"))], headers=alice)
        assert multi.status_code == 201, multi.text
        assert len(multi.json()["files"]) == 2
        assert len((await client.get(f"/api/v1/orders/{order_id}/files", headers=alice)).json()) == 4
        assert (await client.get(f"/api/v1/orders/{order_id}/files", headers=bob)).status_code == 404
        assert len(list(storage.rglob("*"))) > 0
    exercise(tmp_path, monkeypatch, scenario)


def test_zip_extract_and_unsupported_entry(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = zip_bytes({"folder/invoice.png": png_bytes(), "notes.txt": b"not supported"})
        response = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "invoice_image"}, files={"file": ("batch.zip", content, "application/zip")}, headers={"X-User-Id": "alice"})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["archive"]["validation_status"] == "valid"
        assert body["archive"]["sha256"] == hashlib.sha256(content).hexdigest()
        assert [item["validation_status"] for item in body["entries"]] == ["valid", "unsupported"]
        assert all(item["archive_file_id"] == body["archive"]["id"] for item in body["entries"])
        assert body["entries"][0]["archive_entry_path"] == "folder/invoice.png"
    exercise(tmp_path, monkeypatch, scenario)


def test_zip_path_traversal_and_nested_rejected(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        headers = {"X-User-Id": "alice"}
        for content, code in [(zip_bytes({"../escape.png": png_bytes()}), "unsafe_archive_path"), (zip_bytes({"inner.zip": zip_bytes({"x.png": png_bytes()})}), "nested_archive")]:
            response = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "invoice_image"}, files={"file": ("batch.zip", content, "application/zip")}, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
        records = (await client.get(f"/api/v1/orders/{order_id}/files", headers=headers)).json()
        assert len(records) == 2
        assert all(item["file_category"] == "archive" and item["validation_status"] == "invalid" for item in records)
    exercise(tmp_path, monkeypatch, scenario)


def test_zip_file_count_limit(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        response = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "invoice_image"}, files={"file": ("batch.zip", zip_bytes({"a.png": png_bytes(), "b.png": png_bytes()}), "application/zip")}, headers={"X-User-Id": "alice"})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "archive_file_limit"
    exercise(tmp_path, monkeypatch, scenario, max_archive_files=1)


def test_zip_decompressed_size_limit(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        response = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "supporting_material"}, files={"file": ("batch.zip", zip_bytes({"a.txt": b"x" * 32}), "application/zip")}, headers={"X-User-Id": "alice"})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "archive_entry_too_large"
    exercise(tmp_path, monkeypatch, scenario, max_archive_entry_bytes=16)


def test_direct_unsupported_file_is_recorded(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        response = await client.post(f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"}, files=[("files", ("invoice.pdf", b"%PDF-1.4", "application/pdf"))], headers={"X-User-Id": "alice"})
        assert response.status_code == 201
        assert response.json()["files"][0]["validation_status"] == "unsupported"
    exercise(tmp_path, monkeypatch, scenario)


def test_zip_absolute_path_symlink_and_corruption(tmp_path, monkeypatch) -> None:
    link_buffer = io.BytesIO()
    with zipfile.ZipFile(link_buffer, "w") as archive:
        link = zipfile.ZipInfo("shortcut.png")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"target")

    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        headers = {"X-User-Id": "alice"}
        for content, expected in [
            (zip_bytes({"/absolute.png": png_bytes()}), "unsafe_archive_path"),
            (zip_bytes({"C:/absolute.png": png_bytes()}), "unsafe_archive_path"),
            (link_buffer.getvalue(), "unsafe_archive_path"),
            (b"not a zip", "corrupt_archive"),
        ]:
            result = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "invoice_image"}, files={"file": ("bad.zip", content, "application/zip")}, headers=headers)
            assert result.status_code == 422
            assert result.json()["error"]["code"] == expected
        records = (await client.get(f"/api/v1/orders/{order_id}/files", headers=headers)).json()
        assert len(records) == 4
        assert all(record["validation_status"] == "invalid" for record in records)
    exercise(tmp_path, monkeypatch, scenario)


def test_zip_compression_ratio_and_total_limit(tmp_path, monkeypatch) -> None:
    async def ratio_scenario(client, _storage):
        _, order_id = await create_order(client)
        result = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "supporting_material"}, files={"file": ("ratio.zip", zip_bytes({"huge.txt": b"x" * 10000}), "application/zip")}, headers={"X-User-Id": "alice"})
        assert result.status_code == 413
        assert result.json()["error"]["code"] == "archive_ratio_exceeded"
    exercise(tmp_path / "ratio", monkeypatch, ratio_scenario)

    async def total_scenario(client, _storage):
        _, order_id = await create_order(client)
        result = await client.post(f"/api/v1/orders/{order_id}/archives", data={"file_category": "supporting_material"}, files={"file": ("total.zip", zip_bytes({"a.txt": b"a" * 12, "b.txt": b"b" * 12}), "application/zip")}, headers={"X-User-Id": "alice"})
        assert result.status_code == 413
        assert result.json()["error"]["code"] == "archive_total_too_large"
    exercise(tmp_path / "total", monkeypatch, total_scenario, max_archive_total_bytes=16)


def test_production_rejects_simulated_identity(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()

    async def check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get("/api/v1/studios", headers={"X-User-Id": "alice"})
            assert result.status_code == 503
            assert result.json()["error"]["code"] == "authentication_unavailable"

    asyncio.run(check())
    get_settings.cache_clear()


def test_upload_size_preflight_and_image_content_check(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        headers = {"X-User-Id": "alice"}
        oversized = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
            files=[("files", ("good.png", png_bytes(), "image/png")), ("files", ("big.png", b"x" * 128, "image/png"))], headers=headers,
        )
        assert oversized.status_code == 413
        assert (await client.get(f"/api/v1/orders/{order_id}/files", headers=headers)).json() == []
        fake_image = await client.post(
            f"/api/v1/orders/{order_id}/files", data={"file_category": "invoice_image"},
            files=[("files", ("fake.png", b"not an image", "image/png"))], headers=headers,
        )
        assert fake_image.status_code == 201
        assert fake_image.json()["files"][0]["validation_status"] == "invalid"
    exercise(tmp_path, monkeypatch, scenario, max_image_bytes=100)
