from test_stage2 import exercise


def test_old_console_redirects_to_frontend_and_assets_are_not_served(tmp_path, monkeypatch):
    async def scenario(client, _):
        for old, new in [
            ("/console/", "/owner/"),
            ("/console/index.html", "/owner/"),
            ("/console/dashboard.html", "/owner/dashboard/"),
        ]:
            response = await client.get(old, follow_redirects=False)
            assert response.status_code == 307
            assert response.headers["location"] == "http://127.0.0.1:3210" + new
        for path in ["/console/js/live.js", "/console/css/style.css", "/console/unknown.html"]:
            assert (await client.get(path)).status_code == 404

    exercise(tmp_path, monkeypatch, scenario)
