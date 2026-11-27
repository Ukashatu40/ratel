#!/usr/bin/env python3
"""Tests for apply-prepaid.py. `python3 -I test_apply_prepaid.py`

Runs on the configuration of record (network/voice/stack, the files as they are on the voice VM),
with the SMSC's 555 change applied first as it is live. Docker is faked: the Kamailio check itself
runs on the voice VM, and test_prepaid_route.py runs the P-CSCF routes in a real Kamailio.
"""

# ruff: noqa: T201  (a test script run by hand: it prints its report)

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACK = HERE.parent / "stack"
sys.dont_write_bytecode = True


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load(HERE / "apply-prepaid.py", "apply_prepaid")
short = load(HERE.parent / "ussd" / "apply-smsc-shortcode.py", "apply_smsc_shortcode")


def fake_tree() -> Path:
    """~/docker_open5gs as on the voice VM: the stack files, the SMSC with its 555 change."""
    root = Path(tempfile.mkdtemp(prefix="docker_open5gs-"))
    shutil.copytree(STACK / "pcscf", root / "pcscf")
    shutil.copytree(STACK / "smsc", root / "smsc")
    smsc = root / "smsc" / "kamailio_smsc.cfg"
    if "RATEL SHORT" not in smsc.read_text():
        smsc.write_text(short.patch(smsc.read_text()))
    return root


class FakeDocker:
    """Plays `docker exec`: serves the container's files from the fake tree, records the commands,
    and answers kamailio -c with `verdict`."""

    def __init__(self, root: Path, verdict: str = "config file ok, exiting..."):
        self.root, self.verdict, self.commands = root, verdict, []

    def __call__(self, args, input=None, **_):
        after = args[args.index("exec") + 1 :]
        container, command = after[1] if after[0] == "-i" else after[0], args[-1]
        self.commands.append((container, command))
        out, code = "", 0
        if command.startswith("cat /etc/"):
            inside = command.split()[1].split("/", 3)[3]
            path = self.root / container / inside
            out, code = (path.read_text(), 0) if path.exists() else ("", 1)
        elif "kamailio -c" in command:
            out = self.verdict
            code = 0 if "ok" in self.verdict else 255
        return subprocess.CompletedProcess(args, code, out, "")


def strip_prepaid(root: Path) -> None:
    """The record (network/voice/stack) holds the prepaid change; the VM does not have it yet."""
    for rel in ("pcscf/kamailio_pcscf.cfg", "pcscf/route/mo.cfg", "smsc/kamailio_smsc.cfg"):
        path = root / rel
        text = path.read_text()
        for block in (
            tool.MODULES_BLOCK,
            tool.INCLUDE_BLOCK,
            tool.INDIALOG_BLOCK,
            tool.MO_BLOCK,
            tool.REPLY_BLOCK,
            tool.SMSC_BLOCK,
        ):
            text = text.replace(block, "")
        path.write_text(text)
    (root / "pcscf" / "route" / tool.ROUTE_FILE).unlink(missing_ok=True)


def main() -> int:
    failures = 0

    def check(name: str, ok: bool, detail: object = ""):
        nonlocal failures
        print(f"   {'ok ' if ok else 'FAIL'} {name}{f' -> {detail}' if detail and not ok else ''}")
        failures += not ok

    root = fake_tree()
    strip_prepaid(root)
    before = {p: p.read_text() for p in root.rglob("*.cfg")}
    for path in before:
        check(f"starts without the change: {path.relative_to(root)}", tool.MARK not in before[path])

    # the patches themselves
    main_cfg = tool.patch_pcscf_main((root / "pcscf/kamailio_pcscf.cfg").read_text())
    check(
        "loads http_client unless WITH_N5 does",
        '#!ifndef WITH_N5\nloadmodule "http_client.so"' in main_cfg,
    )
    check(
        "includes the route file after mt.cfg",
        'include_file "route/mt.cfg"\n# RATEL PREPAID' in main_cfg,
    )
    i_dlg, i_loose = (
        main_cfg.index("route(RATEL_PREPAID_INDIALOG)"),
        main_cfg.index("if (loose_route())", main_cfg.index("route[WITHINDLG]")),
    )
    check("in-dialog requests are seen before loose_route()", i_dlg < i_loose)
    mo = tool.patch_mo((root / "pcscf/route/mo.cfg").read_text())
    check(
        "the INVITE is asked about at the end of route[MO]",
        'route(RATEL_PREPAID_AUTHORIZE);\n\t}\n\tset_dlg_profile("orig");' in mo,
    )
    check("replies to it are seen", "onreply_route[MO_reply] {\n\t# RATEL PREPAID" in mo)
    smsc = tool.patch_smsc((root / "smsc/kamailio_smsc.cfg").read_text())
    i_charge, i_route = (
        smsc.index("/sms/charge"),
        smsc.index("route(SMS);", smsc.index("route[SMS_FROM_3GPP]")),
    )
    check(
        "texts are charged after the 555 check and the number rewrite, before queueing",
        smsc.index('"^[+]?555$"') < smsc.index('"^0[0-9]{10}$"') < i_charge < i_route,
    )
    try:
        tool.patch_mo("route[MO] {\n}\n")
        check("a file it does not know is refused", False)
    except ValueError as e:
        check(
            "a file it does not know is refused",
            "MO_reply" in str(e) or "set_dlg_profile" in str(e),
            e,
        )

    # the tool: dry run, refusal, apply, second run
    docker = FakeDocker(root)
    code = tool.main([str(root)], run=docker)
    after = {p: p.read_text() for p in root.rglob("*.cfg")}
    check("a dry run writes nothing", code == 0 and after == before, code)
    check(
        "a dry run checks both containers",
        {c for c, cmd in docker.commands if "kamailio -c" in cmd} == {"pcscf", "smsc"},
    )
    check(
        "the check runs from the copy, so includes resolve to it",
        all(
            cmd.startswith(f"cd {tool.CHECK_DIR} && kamailio -c")
            for _, cmd in docker.commands
            if "kamailio -c" in cmd
        ),
    )
    refused = FakeDocker(root, "ERROR: <core> [core/cfg.y:3918]: yyerror_at(): parse error")
    code = tool.main([str(root), "--apply"], run=refused)
    check(
        "a refused check writes nothing, even with --apply",
        code == 1 and {p: p.read_text() for p in root.rglob("*.cfg")} == before,
        code,
    )
    code = tool.main([str(root), "--apply"], run=FakeDocker(root))
    route = root / "pcscf/route" / tool.ROUTE_FILE
    check(
        "--apply writes the four files",
        code == 0
        and route.read_text() == tool.route_file()
        and tool.MARK in (root / "pcscf/kamailio_pcscf.cfg").read_text()
        and tool.MARK in (root / "pcscf/route/mo.cfg").read_text()
        and tool.MARK in (root / "smsc/kamailio_smsc.cfg").read_text(),
        code,
    )
    backups = sorted(p.name.split(".bak-prepaid-")[0] for p in root.rglob("*.bak-prepaid-*"))
    check(
        "and backs up the three it changed",
        backups == ["kamailio_pcscf.cfg", "kamailio_smsc.cfg", "mo.cfg"],
        backups,
    )
    docker = FakeDocker(root)
    code = tool.main([str(root), "--apply"], run=docker)
    check(
        "a second run changes nothing and checks nothing", code == 0 and not docker.commands, code
    )

    # the record of the configuration holds the change too
    for rel in ("pcscf/kamailio_pcscf.cfg", "pcscf/route/mo.cfg", "smsc/kamailio_smsc.cfg"):
        check(
            f"network/voice/stack/{rel} is the applied file",
            (STACK / rel).read_text() == (root / rel).read_text(),
        )
    check(
        "network/voice/stack/pcscf/route has the route file",
        (STACK / "pcscf/route" / tool.ROUTE_FILE).read_text() == tool.route_file(),
    )
    shutil.rmtree(root, ignore_errors=True)
    print("ALL PASSED" if failures == 0 else f"{failures} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
