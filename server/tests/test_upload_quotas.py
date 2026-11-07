from test_stage2 import create_order, exercise, png_bytes, zip_bytes


def test_total_upload_request_limit(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        image = png_bytes()
        response = await client.post(f"/api/v1/orders/{order_id}/files",
                                     data={"file_category": "invoice_image"},
                                     files=[("files", ("a.png", image, "image/png")),
                                            ("files", ("b.png", image, "image/png"))],
                                     headers={"X-User-Id": "alice"})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "upload_request_too_large"
        assert (await client.get(f"/api/v1/orders/{order_id}/files",
                                 headers={"X-User-Id": "alice"})).json() == []

    exercise(tmp_path, monkeypatch, scenario, max_upload_request_bytes=len(png_bytes()) + 1)


def test_archive_quotas_accumulate_across_requests(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage) -> None:
        _, order_id = await create_order(client)
        raw = zip_bytes({"one.png": png_bytes()})
        path = f"/api/v1/orders/{order_id}/archives"
        headers = {"X-User-Id": "alice"}
        first = await client.post(path, data={"file_category": "invoice_image"},
                                  files={"file": ("one.zip", raw, "application/zip")}, headers=headers)
        assert first.status_code == 201
        second = await client.post(path, data={"file_category": "invoice_image"},
                                   files={"file": ("two.zip", raw, "application/zip")}, headers=headers)
        assert second.status_code == 413
        assert second.json()["error"]["code"] == "order_archive_quota"

    raw_size = len(zip_bytes({"one.png": png_bytes()}))
    exercise(tmp_path, monkeypatch, scenario, max_order_archive_bytes=raw_size + 1)
