"""Admin CLI for RatelLink. Run on core-cp as the service user (docs/runbooks/ratel-link.md).

    python -m ratel_link.admin_cli init-db
    python -m ratel_link.admin_cli key generate --out /path/to/ratel_link.key
    python -m ratel_link.admin_cli api-key create --id bss-app --name "RatelBSS"
    python -m ratel_link.admin_cli api-key rotate --id bss-app
    python -m ratel_link.admin_cli api-key revoke --id bss-app --generation 1
    python -m ratel_link.admin_cli api-key disable --id bss-app
    python -m ratel_link.admin_cli api-key list
    python -m ratel_link.admin_cli api-key check-expiry

A new API key is printed once, to stdout, and never goes through the logging system. No option
accepts a key. Nothing here prints a hash or the encryption key.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError
from pymongo.errors import PyMongoError

from common.logging import configure_logging
from common.timeutil import utc_now
from ratel_link import auth
from ratel_link.auth import ApiKeyError, KeyPolicy
from ratel_link.config import Settings
from ratel_link.key_provider import write_new_key_file
from ratel_link.models import ApiKeyGeneration
from ratel_link.repositories import (
    ApiKeyRepository,
    MongoApiKeyRepository,
    ensure_indexes,
    open_database,
)


@dataclass(frozen=True)
class Services:
    api_keys: ApiKeyRepository
    policy: KeyPolicy
    now: Callable[[], datetime]
    create_indexes: Callable[[], list[str]]
    out: TextIO
    err: TextIO


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="admin_cli", description="RatelLink administration.")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init-db", help="create the unique indexes (safe to run again)")

    key = commands.add_parser("key", help="encryption key file").add_subparsers(
        dest="action", required=True
    )
    generate = key.add_parser("generate", help="write a new random key file, never overwriting")
    generate.add_argument("--out", required=True, type=Path, help="path of the new key file")

    api = commands.add_parser("api-key", help="API keys of calling systems").add_subparsers(
        dest="action", required=True
    )
    create = api.add_parser("create", help="register a calling system and print its first key")
    create.add_argument("--id", required=True, help="api_key_id, for example bss-app")
    create.add_argument("--name", required=True, help="human name of the calling system")
    rotate = api.add_parser("rotate", help="add a new key; the old one stops after the overlap")
    rotate.add_argument("--id", required=True)
    revoke = api.add_parser("revoke", help="end one key immediately")
    revoke.add_argument("--id", required=True)
    revoke.add_argument("--generation", required=True, type=int)
    disable = api.add_parser("disable", help="stop every key of a calling system")
    disable.add_argument("--id", required=True)
    api.add_parser("list", help="show systems and key lifetimes (never keys or hashes)")
    api.add_parser("check-expiry", help="log api_key.expiring for keys close to expiry")
    return parser


def _generation_state(g: ApiKeyGeneration, now: datetime) -> str:
    if g.revoked_at is not None:
        return "revoked"
    return "expired" if g.expires_at <= now else "valid"


def _when(value: datetime | None) -> str:
    return "-" if value is None else value.isoformat(timespec="seconds")


def _show_new_key(svc: Services, token: str, api_key_id: str, generation: int) -> None:
    svc.out.write(token + "\n")  # stdout only. This is the one and only time it is shown.
    svc.err.write(
        f"api_key_id={api_key_id} generation={generation}. "
        "Copy the key above into an owner-only env file on the calling host now. "
        "It cannot be shown again.\n"
    )


def run(args: argparse.Namespace, svc: Services) -> int:
    """Run one parsed command. Returns the process exit code."""
    now = svc.now()
    try:
        if args.command == "init-db":
            for name in svc.create_indexes():
                svc.out.write(f"index ready: {name}\n")
        elif args.action == "create":
            token = auth.create_system(svc.api_keys, args.id, args.name, now, svc.policy)
            _show_new_key(svc, token, args.id, 1)
        elif args.action == "rotate":
            token = auth.rotate(svc.api_keys, args.id, now, svc.policy)
            record = svc.api_keys.get(args.id)
            generation = max(g.generation for g in record.generations) if record else 0
            _show_new_key(svc, token, args.id, generation)
        elif args.action == "revoke":
            auth.revoke(svc.api_keys, args.id, args.generation, now)
            svc.out.write(f"revoked {args.id} generation {args.generation}\n")
        elif args.action == "disable":
            auth.disable(svc.api_keys, args.id)
            svc.out.write(f"disabled {args.id}\n")
        elif args.action == "list":
            for record in svc.api_keys.list_all():
                svc.out.write(f"{record.api_key_id}  {record.system_name}  {record.status}\n")
                for g in record.generations:
                    svc.out.write(
                        f"  generation {g.generation}  {_generation_state(g, now):<7}  "
                        f"created {_when(g.created_at)}  expires {_when(g.expires_at)}  "
                        f"revoked {_when(g.revoked_at)}\n"
                    )
        elif args.action == "check-expiry":
            expiring = auth.log_expiring(svc.api_keys, now, svc.policy)
            svc.err.write(f"{len(expiring)} key(s) expire within {svc.policy.warn_days} days\n")
    except ApiKeyError as exc:
        svc.err.write(f"error: {exc}\n")
        return 1
    return 0


def _generate_key_file(path: Path, err: TextIO) -> int:
    try:
        write_new_key_file(path)
    except FileExistsError:
        err.write(f"error: {path} already exists. Refusing to overwrite a key file.\n")
        return 1
    except OSError as exc:
        err.write(f"error: cannot write {path}: {exc.strerror}\n")
        return 1
    err.write(
        f"Wrote a new 32-byte key to {path} (owner-only). Set RATEL_LINK_KEY_FILE to this path. "
        "Back it up offline, separately from database backups: without it every stored Ki "
        "and OPc is lost.\n"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (args.command, getattr(args, "action", None)) == ("key", "generate"):
        return _generate_key_file(args.out, sys.stderr)
    try:
        settings = Settings()
    except ValidationError as exc:
        # Field names only: the input may be a connection string with credentials.
        fields = sorted({".".join(map(str, e["loc"])) or "settings" for e in exc.errors()})
        sys.stderr.write("error: invalid configuration: " + ", ".join(fields) + "\n")
        return 2
    # stdout carries a new API key. Log lines must never share it.
    configure_logging(settings.log_level, stream=sys.stderr)
    database = open_database(settings)
    services = Services(
        api_keys=MongoApiKeyRepository(database),
        policy=KeyPolicy.from_settings(settings),
        now=utc_now,
        create_indexes=lambda: ensure_indexes(database),
        out=sys.stdout,
        err=sys.stderr,
    )
    try:
        return run(args, services)
    except PyMongoError as exc:
        sys.stderr.write(f"error: database request failed ({type(exc).__name__})\n")
        return 1
    finally:
        database.client.close()


if __name__ == "__main__":
    sys.exit(main())
