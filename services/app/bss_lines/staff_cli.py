"""Make and manage RatelDesk staff accounts. Run by a person on bss-app, never by a timer.

    python -m app.bss_lines.staff_cli create --email E --name NAME --role agent|admin
    python -m app.bss_lines.staff_cli reset-password --email E
    python -m app.bss_lines.staff_cli disable --email E
    python -m app.bss_lines.staff_cli enable --email E
    python -m app.bss_lines.staff_cli list

The password is never an argument (it would sit in the shell history and the process list). It is
typed twice at a prompt, or, with `--password-stdin`, read from one line of standard input. Nothing
here prints a password, a hash or an email other than in `list`.

This is how the first admin is made: there is no sign-up route, and no default account.

Exit 0: done. Exit 1: refused (bad input, an email already in use, no such account). Exit 2: could
not run (the database did not answer).
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from app.bss_lines.domain.staff import Role
from app.bss_lines.repositories.desk_ports import DuplicateStaff
from app.bss_lines.repositories.desk_sql import SqlStaffRepository
from app.bss_lines.services import staff_auth
from app.config import Settings
from app.db import make_engine, session_factory
from common.logging import configure_logging, log_event

log = logging.getLogger("ratel.bss.lines.staff")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="staff_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("create")
    make.add_argument("--email", required=True)
    make.add_argument("--name", required=True)
    make.add_argument("--role", required=True, choices=[r.value for r in Role])
    reset = commands.add_parser("reset-password")
    reset.add_argument("--email", required=True)
    for name in ("disable", "enable"):
        commands.add_parser(name).add_argument("--email", required=True)
    commands.add_parser("list")
    for name in ("create", "reset-password"):
        commands.choices[name].add_argument(
            "--password-stdin", action="store_true", help="read the password from one line of stdin"
        )
    return parser


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password: ")
    if getpass.getpass("Again: ") != first:
        raise ValueError("the two passwords differ")
    return first


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.log_level, stream=sys.stderr)
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        with session_factory(engine)() as session, session.begin():
            return _run(SqlStaffRepository(session), args)
    except DuplicateStaff:
        sys.stderr.write("refused: an account with that email exists already\n")
        return 1
    except ValueError as exc:
        sys.stderr.write(f"refused: {exc}\n")
        return 1
    except SQLAlchemyError as exc:
        # Type only: a driver message can carry the database host and user.
        log_event(log, logging.ERROR, "staff.cli_failed", exc_type=type(exc).__name__)
        return 2
    finally:
        engine.dispose()


def _run(staff: SqlStaffRepository, args: argparse.Namespace) -> int:
    if args.command == "create":
        password = _read_password(args.password_stdin)
        made = staff_auth.create_staff(
            staff, email=args.email, name=args.name, role=args.role, password=password
        )
        sys.stderr.write(f"account {made.staff_id} made ({made.role})\n")
        return 0
    if args.command == "list":
        for record in staff.all_staff():
            state = "active" if record.active else "disabled"
            sys.stdout.write(f"{record.staff_id}\t{record.role}\t{state}\t{record.email}\n")
        return 0
    if args.command == "reset-password":
        found = staff_auth.reset_password(staff, args.email, _read_password(args.password_stdin))
        done = "password reset; every session of that account ended"
    else:
        found = staff_auth.set_active(staff, args.email, args.command == "enable")
        done = f"account {args.command}d"
    sys.stderr.write(f"{done}\n" if found else "refused: no such account\n")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
