#!/usr/bin/env python3
"""Turns on prepaid control of calls and texts on the voice VM (ADR 0013, docs/catalogue.md).

Changes, all marked "RATEL PREPAID", in ~/docker_open5gs:
  pcscf/route/ratel_prepaid.cfg   new: asks before each call, refuses it (402) or limits it, keeps
                                  the limit through session refreshes, reports the end of the call
  pcscf/kamailio_pcscf.cfg        loads http_client, adds the `prepaid` htable, includes the file
                                  above, and calls it for every in-dialog request (before
                                  loose_route)
  pcscf/route/mo.cfg              calls it for the caller's INVITE and for the replies to it
  smsc/kamailio_smsc.cfg          asks before queueing a text from a phone; a refused text is not
                                  queued (the ussd service tells the sender why, from 555)
The questions go to the ussd container (network/voice/ussd, 172.22.0.40:8647), which relays them to
bss-app. Update and restart that container first (./run-ussd.sh), or every call is limited to the
two-minute fallback until it is.

Before writing, each container's own Kamailio checks its new files (kamailio -c, run on a copy of
the container's configuration), and nothing is written when either refuses. `--no-check` skips that
(only where the containers are not running). A file that has the change already is left alone.

Usage (on the voice VM):
  python3 apply-prepaid.py ~/docker_open5gs            dry run: shows the changes and the checks
  python3 apply-prepaid.py ~/docker_open5gs --apply    checks, backs up, writes
Then: docker restart smsc, and ~/ratel-ussd/network/voice/stack/restart-pcscf.sh.
Rollback: copy back the backups it names (and remove pcscf/route/ratel_prepaid.cfg), then restart
both containers the same way.
"""

# ruff: noqa: T201  (a command-line tool: printing is its output)

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARK = "RATEL PREPAID"
ROUTE_FILE = "ratel_prepaid.cfg"

# --- pcscf/kamailio_pcscf.cfg ------------------------------------------------------------------

MODULES_ANCHOR = '# HTable as a cache:\nloadmodule "htable.so"\n'
MODULES_BLOCK = """
# RATEL PREPAID (ADR 0013): the P-CSCF asks bss-app, through the ussd container, before each call
# (route/ratel_prepaid.cfg). http_client is loaded here unless WITH_N5 has loaded it already.
#!ifndef WITH_N5
loadmodule "http_client.so"
#!endif
modparam("http_client", "connection_timeout", 2)
modparam("htable", "htable", "prepaid=>size=10;autoexpire=11700")
"""

INCLUDE_ANCHOR = 'include_file "route/mt.cfg"\n'
INCLUDE_BLOCK = f'# RATEL PREPAID (ADR 0013)\ninclude_file "route/{ROUTE_FILE}"\n'

INDIALOG_ANCHOR = "route[WITHINDLG] {\n\tif (has_totag()) {\n"
INDIALOG_BLOCK = (
    "\t\t# RATEL PREPAID: what is left of a limited call, before loose_route() restarts its timer\n"
    "\t\troute(RATEL_PREPAID_INDIALOG);\n"
)

# --- pcscf/route/mo.cfg ------------------------------------------------------------------------

MO_ANCHOR = '\tset_dlg_profile("orig");\n\tt_on_reply("MO_reply");\n}\n'
MO_BLOCK = (
    "\t# RATEL PREPAID (ADR 0013): ask before the call, then refuse it or limit it\n"
    '\tif (is_method("INVITE")) {\n'
    "\t\troute(RATEL_PREPAID_AUTHORIZE);\n"
    "\t}\n"
)

REPLY_ANCHOR = "onreply_route[MO_reply] {\n"
REPLY_BLOCK = "\t# RATEL PREPAID: answered, or not answered\n\troute(RATEL_PREPAID_REPLY);\n"

# --- smsc/kamailio_smsc.cfg --------------------------------------------------------------------

SMSC_ANCHOR = "\t\t$avp(text) = $tpdu(payload);\n"
SMSC_BLOCK = r"""		# RATEL PREPAID (ADR 0013): ask before queueing a text from a phone.
		# 402: not sent (the phone already has its RP-ACK; the ussd service tells
		# the sender why, from 555). No answer: sent.
		$var(url) = "http://172.22.0.40:8647/sms/charge?id=";
		$var(url) = $var(url) + $(ci{s.urlencode.param});
		$var(url) = $var(url) + "&from=" + $(avp(from){s.urlencode.param});
		$var(url) = $var(url) + "&to=" + $(avp(to){s.urlencode.param});
		$var(charge) = "";
		http_client_query("$var(url)", "$var(charge)");
		$var(code) = $retcode;
		if ($var(code) == 402) {
			xnotice("SMSC: text $ci not sent ($var(charge))\n");
			exit;
		}
		if ($var(code) != 200) {
			xlog("L_WARN", "SMSC: no charge answer for $ci ($var(code)): sent unchecked\n");
		}
"""

Edit = tuple[str, str, bool]  # anchor, block, True: block goes before the anchor


def insert(text: str, edits: list[Edit], what: str) -> str:
    """`text` with each block next to its anchor. ValueError when an anchor is not there once."""
    for anchor, block, before in edits:
        found = text.count(anchor)
        if found != 1:
            raise ValueError(f"{what}: expected exactly one {anchor.strip()!r}, found {found}")
        text = text.replace(anchor, block + anchor if before else anchor + block, 1)
    return text


def patch_pcscf_main(text: str) -> str:
    return insert(
        text,
        [
            (MODULES_ANCHOR, MODULES_BLOCK, False),
            (INCLUDE_ANCHOR, INCLUDE_BLOCK, False),
            (INDIALOG_ANCHOR, INDIALOG_BLOCK, False),
        ],
        "kamailio_pcscf.cfg",
    )


def patch_mo(text: str) -> str:
    return insert(
        text, [(MO_ANCHOR, MO_BLOCK, True), (REPLY_ANCHOR, REPLY_BLOCK, False)], "route/mo.cfg"
    )


def patch_smsc(text: str) -> str:
    return insert(text, [(SMSC_ANCHOR, SMSC_BLOCK, False)], "kamailio_smsc.cfg")


def route_file() -> str:
    return (HERE / ROUTE_FILE).read_text()


# Each changed file: (container, path under ~/docker_open5gs, path in the container, patch).
FILES: list[tuple[str, str, str, Callable[[str], str] | None]] = [
    ("pcscf", "pcscf/kamailio_pcscf.cfg", "kamailio_pcscf.cfg", patch_pcscf_main),
    ("pcscf", "pcscf/route/mo.cfg", "route/mo.cfg", patch_mo),
    ("pcscf", f"pcscf/route/{ROUTE_FILE}", f"route/{ROUTE_FILE}", None),  # whole file
    ("smsc", "smsc/kamailio_smsc.cfg", "kamailio_smsc.cfg", patch_smsc),
]
LIVE = {
    "pcscf": ("/etc/kamailio_pcscf", "kamailio_pcscf.cfg"),
    "smsc": ("/etc/kamailio_smsc", "kamailio_smsc.cfg"),
}
CHECK_DIR = "/tmp/ratel-prepaid-check"  # noqa: S108  (inside the container, removed after)


def new_content(current: str | None, change: Callable[[str], str] | None) -> str | None:
    """The file with the change, or None when it has it already."""
    if change is None:
        wanted = route_file()
        return None if current == wanted else wanted
    if current is None:
        raise ValueError("the file is missing")
    if MARK in current:
        return None
    return change(current)


Run = Callable[..., subprocess.CompletedProcess[str]]


def kamailio_check(container: str, run: Run) -> tuple[bool, str]:
    """Copy the container's live configuration, apply the change to the copy, and have the
    container's Kamailio check it (kamailio -c, from that folder, so includes resolve to the copy).
    """
    live_dir, main_file = LIVE[container]

    def sh(command: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = [
            "docker",
            "exec",
            *(["-i"] if stdin is not None else []),
            container,
            "sh",
            "-c",
            command,
        ]
        return run(args, input=stdin, capture_output=True, text=True, timeout=60)

    try:
        made = sh(f"rm -rf {CHECK_DIR} && cp -r {live_dir} {CHECK_DIR}")
        if made.returncode != 0:
            return (
                False,
                f"could not copy {live_dir} in the {container} container: {made.stderr.strip()}",
            )
        for owner, _, inside, change in FILES:
            if owner != container:
                continue
            got = sh(f"cat {live_dir}/{inside} 2>/dev/null")
            current = got.stdout if got.returncode == 0 else None
            try:
                text = new_content(current, change)
            except ValueError as e:
                return False, f"{container} {inside}: {e}"
            if text is not None:
                put = sh(f"cat > {CHECK_DIR}/{inside}", stdin=text)
                if put.returncode != 0:
                    return False, f"could not write the copy of {inside}: {put.stderr.strip()}"
        done = sh(f"cd {CHECK_DIR} && kamailio -c -f {CHECK_DIR}/{main_file}")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"could not run the check: {type(e).__name__}"
    finally:
        try:
            sh(f"rm -rf {CHECK_DIR}")
        except (OSError, subprocess.SubprocessError):
            pass
    said = (done.stdout + done.stderr).strip()
    errors = [line for line in said.splitlines() if "ERROR" in line or "CRITICAL" in line]
    if done.returncode != 0 or errors:
        return False, "\n".join(errors[-8:]) or said[-800:]
    return True, ""


def main(argv: list[str] | None = None, run: Run = subprocess.run) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0].startswith("-"):
        print(__doc__)
        return 2
    root, apply, checked = (
        Path(os.path.expanduser(args[0])),
        "--apply" in args[1:],
        "--no-check" not in args[1:],
    )
    changes: list[tuple[Path, str]] = []
    for _, rel, _, change in FILES:
        path = root / rel
        current = path.read_text() if path.exists() else None
        try:
            text = new_content(current, change)
        except ValueError as e:
            print(f"{rel}: {e}; nothing changed")
            return 1
        if text is None:
            print(f"{rel}: has the change already")
            continue
        changes.append((path, text))
        print(f"{rel}: will be {'written' if current is None else 'changed'}")
    if not changes:
        print("nothing to do")
        return 0
    if checked:
        for container in ("pcscf", "smsc"):
            ok, said = kamailio_check(container, run)
            if not ok:
                print(
                    f"\nthe {container} container's Kamailio refuses the new configuration:\n{said}"
                )
                print("nothing written" if apply else "dry run: nothing written")
                return 1
            print(
                f"the {container} container's Kamailio accepts the new configuration (kamailio -c)"
            )
    if not apply:
        print("\ndry run: nothing written. Run again with --apply to write it.")
        return 0
    stamp = time.strftime("%Y%m%d%H%M")
    for path, text in changes:
        if path.exists():
            backup = path.with_name(f"{path.name}.bak-prepaid-{stamp}")
            shutil.copy2(path, backup)
            print(f"backup: {backup}")
        path.write_text(text)
        print(f"written: {path}")
    print(
        "\nnext: docker restart smsc, then restart-pcscf.sh (the ussd container first, if not done)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
