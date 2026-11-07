"""Mark stale running tasks timed out and optionally queue bounded retries."""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.exceptions import AppError
from app.db.session import make_engine
from app.services.agent_service import retry_task, timeout_stale_tasks


async def recover(retry: bool) -> None:
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            timed_out = await timeout_stale_tasks(db)
            for task in timed_out:
                if retry:
                    try:
                        await retry_task(db, task.id)
                        print(f"{task.id}: retrying")
                    except AppError as exc:
                        print(f"{task.id}: timeout; retry unavailable ({exc.code})")
                else:
                    print(f"{task.id}: timeout")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry", action="store_true", help="Queue eligible timed-out tasks for retry")
    args = parser.parse_args()
    asyncio.run(recover(args.retry))


if __name__ == "__main__":
    main()
