"""Administrator accounts from the server.

    python -m app.cli create-admin admin@example.com
    python -m app.cli reset-password admin@example.com
"""

import argparse
import asyncio
import getpass
import sys

from app.core.db import engine
from app.services.admins import AdminError, create_admin, reset_password


def _ask_password() -> str:
    # Never an argument: it would end up in the shell history and the process list.
    password = getpass.getpass("Mot de passe : ")
    if password != getpass.getpass("Confirmation : "):
        raise AdminError("Les deux mots de passe ne correspondent pas.")
    return password


async def _run(action, email: str, password: str) -> None:
    try:
        await action(email, password)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "reset-password"):
        commands.add_parser(name).add_argument("email")
    args = parser.parse_args()

    action = create_admin if args.command == "create-admin" else reset_password
    try:
        asyncio.run(_run(action, args.email, _ask_password()))
    except AdminError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
