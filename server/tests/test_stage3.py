from test_stage2 import create_order, exercise


async def upload_csv(client, order_id: str, content: bytes, user: str = "alice") -> str:
    response = await client.post(
        f"/api/v1/orders/{order_id}/files",
        data={"file_category": "bank_statement_csv"},
        files=[("files", ("bank.csv", content, "text/csv"))],
        headers={"X-User-Id": user},
    )
    assert response.status_code == 201, response.text
    return response.json()["files"][0]["id"]


def test_import_persists_valid_and_error_rows(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        content = (
            "transaction_date,counterparty,direction,amount,description,external_id\n"
            "2026-10-01,ＡＣＭＥ   Co,IN,12.34,design,tx-1\n"
            "2026-10-02,B,OUT,1.234,invalid,tx-2\n"
            "2026-10-03,C,OUT,5.00,hosting,tx-3\n"
        ).encode("utf-8-sig")
        file_id = await upload_csv(client, order_id, content)
        headers = {"X-User-Id": "alice"}
        response = await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=headers)
        assert response.status_code == 201, response.text
        result = response.json()
        assert (result["total_rows"], result["success_rows"], result["failed_rows"]) == (3, 2, 1)
        assert result["errors"][0]["row_number"] == 3
        assert result["errors"][0]["reason"] == "amount_precision"
        assert result["errors"][0]["raw_row_json"]["amount"] == "1.234"
        transactions = (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=headers)).json()
        assert len(transactions) == 2
        assert transactions[0]["amount_cents"] == 1234
        assert transactions[0]["normalized_counterparty"] == "acme co"
        assert transactions[0]["raw_row_json"]["counterparty"] == "ＡＣＭＥ   Co"
        assert len((await client.get(f"/api/v1/orders/{order_id}/imports", headers=headers)).json()) == 1
        assert (await client.get(f"/api/v1/imports/{result['id']}", headers=headers)).json()["failed_rows"] == 1
        repeated = await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=headers)
        assert repeated.status_code == 201
        assert repeated.json()["id"] == result["id"]
        assert len((await client.get(f"/api/v1/orders/{order_id}/transactions", headers=headers)).json()) == 2
    exercise(tmp_path, monkeypatch, scenario)


def test_missing_header_rejects_whole_import(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        file_id = await upload_csv(client, order_id, b"transaction_date,counterparty,amount\n2026-10-01,A,1.00\n")
        headers = {"X-User-Id": "alice"}
        result = await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=headers)
        assert result.status_code == 422
        assert result.json()["error"]["code"] == "missing_csv_columns"
        assert (await client.get(f"/api/v1/orders/{order_id}/imports", headers=headers)).json() == []
    exercise(tmp_path, monkeypatch, scenario)


def test_import_access_control(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        file_id = await upload_csv(client, order_id, b"transaction_date,counterparty,direction,amount\n2026-10-01,A,IN,1.00\n")
        alice = {"X-User-Id": "alice"}
        bob = {"X-User-Id": "bob"}
        assert (await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=bob)).status_code == 404
        result = (await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=alice)).json()
        assert (await client.get(f"/api/v1/imports/{result['id']}", headers=bob)).status_code == 404
        assert (await client.get(f"/api/v1/orders/{order_id}/transactions", headers=bob)).status_code == 404
    exercise(tmp_path, monkeypatch, scenario)


def test_column_map_request_override(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        _, order_id = await create_order(client)
        file_id = await upload_csv(client, order_id, b"Date,Payee,Flow,Value\n2026-10-01,Vendor,OUT,9.99\n")
        mapping = {"transaction_date": "Date", "counterparty": "Payee", "direction": "Flow", "amount": "Value"}
        result = await client.post(
            f"/api/v1/orders/{order_id}/imports/csv",
            json={"file_id": file_id, "column_map": mapping}, headers={"X-User-Id": "alice"},
        )
        assert result.status_code == 201, result.text
        assert result.json()["success_rows"] == 1
        assert result.json()["column_map_json"]["amount"] == "Value"
    exercise(tmp_path, monkeypatch, scenario)


def test_encoding_and_empty_file_errors_at_import(tmp_path, monkeypatch) -> None:
    async def scenario(client, _storage):
        headers = {"X-User-Id": "alice"}
        for content, code in [(b"", "empty_csv"), (b"\xff\xfe", "invalid_csv_encoding")]:
            _, order_id = await create_order(client)
            file_id = await upload_csv(client, order_id, content)
            response = await client.post(f"/api/v1/orders/{order_id}/imports/csv", json={"file_id": file_id}, headers=headers)
            assert response.status_code == 422
            assert response.json()["error"]["code"] == code
    exercise(tmp_path, monkeypatch, scenario)
