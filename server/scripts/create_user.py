"""Interactive local account provisioning after `alembic upgrade head`."""

import argparse
import asyncio
from getpass import getpass

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import make_engine
from app.models import Studio, TenantMembership
from app.services.local_auth import create_user


async def provision(username: str, role: str, studio_id: str | None) -> None:
    engine = make_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            if studio_id and await db.get(Studio, studio_id) is None:
                raise ValueError("Studio does not exist")
            password = getpass("Password (at least 12 characters): ")
            confirmation = getpass("Repeat password: ")
            if password != confirmation:
                raise ValueError("Passwords do not match")
            user = await create_user(db, username, password, role)
            if studio_id:
                db.add(TenantMembership(user_id=user.id, studio_id=studio_id))
                await db.commit()
            print(f"Created user {user.username} ({user.id}), role={role}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--role", choices=["customer", "owner"], default="customer")
    parser.add_argument("--studio-id", help="Explicitly grant access to an existing Studio")
    args = parser.parse_args()
    asyncio.run(provision(args.username, args.role, args.studio_id))


if __name__ == "__main__":
    main()
