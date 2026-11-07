"""Isolated CI browser stack. The model replacement is only available in this test entrypoint."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))


async def scripted_worker():
    from live_support import LiveScriptedRunner

    from app.db.session import SessionLocal
    from app.db.types import utc_now
    from app.live import service
    from app.live.worker import DATA, execute_run

    DATA.mkdir(parents=True, exist_ok=True)
    runner = LiveScriptedRunner()
    while True:
        (DATA / "heartbeat.json").write_text(
            json.dumps({"pid": os.getpid(), "at": utc_now().isoformat()}), encoding="utf-8"
        )
        for kind in ("processing", "chat"):
            token = str(uuid4())
            async with SessionLocal() as session:
                run_id = await service.claim_run(session, kind, token)
            if run_id:
                await execute_run(SessionLocal, run_id, token, runner=runner)
        await asyncio.sleep(0.15)


def main():
    if "--worker" in sys.argv:
        asyncio.run(scripted_worker())
        return
    children = []
    with tempfile.TemporaryDirectory(prefix="ledgercrew-e2e-") as temporary:
        env = os.environ.copy()
        # This stack never loads or calls MiMo. Production Worker has no such fallback.
        env.update(
            DATABASE_URL="sqlite+aiosqlite:///" + Path(temporary, "e2e.db").as_posix(),
            STORAGE_ROOT=str(Path(temporary, "storage")),
            ENVIRONMENT="test",
            LEDGERCREW_LIVE_DATA_DIR=str(Path(temporary, "runtime")),
            LEDGERCREW_API_ORIGIN="http://127.0.0.1:8010",
            LEDGERCREW_NEXT_DIST=".next-e2e",
            PYTHONUTF8="1",
        )
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=SERVER, env=env, check=True)
        try:
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8010",
                    ],
                    cwd=SERVER,
                    env=env,
                )
            )
            children.append(
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()), "--worker"], cwd=SERVER, env=env
                )
            )
            children.append(
                subprocess.Popen(
                    [
                        shutil.which("node") or "node",
                        "node_modules/next/dist/bin/next",
                        "dev",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3211",
                    ],
                    cwd=SERVER.parent / "web",
                    env=env,
                )
            )

            def stop(*_):
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, stop)
            while True:
                for child in children:
                    if child.poll() is not None:
                        raise RuntimeError("E2E service exited")
                import time

                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            for child in reversed(children):
                child.terminate()
            for child in children:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()


if __name__ == "__main__":
    main()
