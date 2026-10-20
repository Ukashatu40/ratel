"""Build Plan, RatelLink "Done when": after a full run, no log file holds a Ki or OPc value.

The pytest session log is searched by tests/conftest.py. This test covers what that cannot see: the
log of a real RatelLink process (the same entry point the systemd unit starts, at debug level so it
says as much as it ever can), and the admin command line, while a line is imported, activated,
changed and deactivated, and while requests fail in every way the contract allows. The keys it
uses are the synthetic ones in tests/synthetic.py, which the search looks for in both cases.

It also looks in the database for the values that must never be stored in the clear. A search that
cannot fail proves nothing, so the last test plants a key in a scratch log and expects it found.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pymongo import MongoClient

from ratel_link.config import Settings
from ratel_link.repositories.mongo import open_database
from tests.synthetic import (
    SYNTHETIC_IMS_SESSION,
    SYNTHETIC_IMSI,
    SYNTHETIC_IMSI_2,
    SYNTHETIC_KI_HEX,
    SYNTHETIC_MSISDN,
    SYNTHETIC_OPC_HEX,
    find_sentinels,
)

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ROOT / "services"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Run:
    """A throwaway RatelLink process with its own databases, and everything it printed."""

    def __init__(self, work: Path, mongo_uri: str) -> None:
        suffix = os.urandom(3).hex()
        self.ratel_db = f"ratel_link_logscan_{suffix}"
        self.core_db = f"open5gs_logscan_{suffix}"
        self.work = work
        self.mongo_uri = mongo_uri
        self.port = _free_port()
        self.server_log = work / "server.log"
        self.cli_log = work / "cli.log"
        template = work / "ims_template.json"
        template.write_text(json.dumps({"slice": [{"session": [SYNTHETIC_IMS_SESSION]}]}))
        self.env = {
            **os.environ,
            "PYTHONPATH": str(SERVICES),
            "MONGO_URI": mongo_uri,
            "RATEL_LINK_DB_NAME": self.ratel_db,
            "OPEN5GS_DB_NAME": self.core_db,
            "RATEL_ENV": "test",
            "RATEL_LINK_KEY_FILE": str(work / "ratel_link.key"),
            "RATEL_LINK_VOICE_TEMPLATE_FILE": str(template),
            "LOG_LEVEL": "DEBUG",
        }
        self.token = ""
        self.process: subprocess.Popen[bytes] | None = None

    def cli(self, *args: str) -> str:
        with self.cli_log.open("ab") as log:
            done = subprocess.run(  # noqa: S603  (our own interpreter and fixed arguments)
                [sys.executable, "-m", "ratel_link.admin_cli", *args],
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=log,
                check=True,
                timeout=60,
            )
        return done.stdout.decode().strip()

    def start(self) -> None:
        self.cli("key", "generate", "--out", self.env["RATEL_LINK_KEY_FILE"])
        self.cli("init-db")
        # stdout of this command is the new API key by design. Only stderr is a log.
        self.token = self.cli("api-key", "create", "--id", "logscan", "--name", "Log scan (test)")
        with self.server_log.open("ab") as log:
            self.process = subprocess.Popen(  # noqa: S603  (our own interpreter and fixed arguments)
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "--factory",
                    "ratel_link.main:create_app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                    "--log-level",
                    "debug",
                    "--no-access-log",
                ],
                env=self.env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{self.port}/healthz", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.3)
        raise AssertionError("RatelLink did not start")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
        client: MongoClient[Any] = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
        client.drop_database(self.ratel_db)
        client.drop_database(self.core_db)
        client.close()

    def logs(self) -> str:
        return "\n".join(
            path.read_text(errors="replace")
            for path in (self.server_log, self.cli_log)
            if path.exists()
        )


@pytest.fixture
def run(tmp_path: Path) -> Iterator[Run]:
    uri = os.environ.get("RATEL_TEST_MONGO_URI")
    if not uri:
        pytest.skip("RATEL_TEST_MONGO_URI is not set")
    started = Run(tmp_path, uri)
    try:
        started.start()
        yield started
    finally:
        started.stop()


def _use_every_operation(run: Run) -> None:
    """A full life of a line, then every kind of failure, with the synthetic keys."""
    keys = {"imsi": SYNTHETIC_IMSI, "ki": SYNTHETIC_KI_HEX, "opc": SYNTHETIC_OPC_HEX}
    body = {"msisdn": SYNTHETIC_MSISDN, "speed_ul_mbps": 5, "speed_dl_mbps": 10, "voice": True}
    line = f"/v1/lines/{SYNTHETIC_IMSI}"
    headers = {"Authorization": f"Bearer {run.token}"}
    with httpx.Client(base_url=f"http://127.0.0.1:{run.port}", timeout=15) as client:
        steps: list[tuple[str, str, Any, int]] = [
            ("POST", "/v1/sims", keys, 200),
            ("POST", "/v1/sims", keys, 200),
            ("POST", "/v1/sims", {**keys, "ki": SYNTHETIC_OPC_HEX}, 409),
            ("POST", "/v1/sims", {**keys, "ki": SYNTHETIC_KI_HEX[:-1] + "z"}, 422),
            ("POST", "/v1/sims", {**keys, "extra": SYNTHETIC_KI_HEX}, 422),
            ("POST", f"{line}/activate", body, 200),
            ("POST", f"{line}/activate", {**body, "speed_dl_mbps": 7}, 200),
            ("POST", f"{line}/data", {"mode": "slow", "speed_ul_mbps": 1, "speed_dl_mbps": 2}, 200),
            ("POST", f"{line}/data", {"mode": "off"}, 200),
            (
                "POST",
                f"{line}/data",
                {"mode": "full", "speed_ul_mbps": 5, "speed_dl_mbps": 10},
                200,
            ),
            ("GET", line, None, 200),
            ("GET", "/v1/assignments", None, 200),
            ("POST", f"{line}/deactivate", {"reason": "log scan"}, 200),
            ("POST", f"{line}/activate", body, 200),
            ("POST", f"/v1/lines/{SYNTHETIC_IMSI_2}/activate", body, 404),
            ("POST", f"{line}/activate", {**body, "msisdn": SYNTHETIC_OPC_HEX}, 422),
        ]
        for method, path, payload, expected in steps:
            reply = client.request(method, path, json=payload, headers=headers)
            assert reply.status_code == expected, (method, path.split("/")[-1], reply.status_code)
            assert not find_sentinels(reply.text), "a key came back in a response"
        # Rejected callers: no key and a wrong key.
        for bad in ({}, {"Authorization": "Bearer rlk_nope.nope"}):
            assert client.post("/v1/sims", json=keys, headers=bad).status_code == 401


@pytest.mark.integration
def test_no_log_of_a_full_run_holds_a_key(run: Run) -> None:
    _use_every_operation(run)
    assert run.process is not None
    run.process.terminate()
    run.process.wait(timeout=15)
    text = run.logs()
    assert "line.activate" in text and "sim.import" in text, "the run left no log to search"
    assert find_sentinels(text) == []
    assert run.token not in text, "the API key reached a log"


@pytest.mark.integration
def test_the_database_holds_no_key_in_the_clear_outside_the_core(run: Run) -> None:
    _use_every_operation(run)
    client: MongoClient[Any] = MongoClient(run.mongo_uri, serverSelectionTimeoutMS=3000)
    try:
        ratel = client[run.ratel_db]
        for name in ratel.list_collection_names():
            dump = json.dumps(list(ratel[name].find({})), default=str)
            assert find_sentinels(dump) == [], f"a key is stored in the clear in {name}"
            assert run.token not in dump, f"the API key is stored in the clear in {name}"
        # The core's collection is the one place the keys are, because Open5GS needs them there.
        core = client[run.core_db]["subscribers"].find_one({"imsi": SYNTHETIC_IMSI})
        assert core is not None and core["security"]["k"] == SYNTHETIC_KI_HEX.upper()
    finally:
        client.close()


def test_the_mongodb_driver_is_kept_quiet_whatever_the_log_level() -> None:
    """At DEBUG the driver logs whole command documents: the update that writes Ki and OPc into the
    core, and the reply that reads them back. Opening the database must stop that."""
    pymongo_log = logging.getLogger("pymongo")
    root = logging.getLogger()
    before = (pymongo_log.level, root.level)
    try:
        root.setLevel(logging.DEBUG)
        pymongo_log.setLevel(logging.NOTSET)
        assert logging.getLogger("pymongo.command").isEnabledFor(logging.DEBUG)  # the problem
        database = open_database(Settings(log_level="DEBUG"))
        try:
            for name in ("pymongo", "pymongo.command", "pymongo.connection", "pymongo.topology"):
                assert not logging.getLogger(name).isEnabledFor(logging.DEBUG), name
        finally:
            database.client.close()
    finally:
        pymongo_log.setLevel(before[0])
        root.setLevel(before[1])


def test_the_search_can_fail(tmp_path: Path) -> None:
    """A key planted in a scratch log is found, in either case, and a clean log is not flagged."""
    scratch = tmp_path / "scratch.log"
    scratch.write_text('{"event": "x", "note": "' + SYNTHETIC_KI_HEX.upper() + '"}\n')
    assert find_sentinels(scratch.read_text()) == [SYNTHETIC_KI_HEX.upper()]
    scratch.write_text('{"event": "x", "note": "' + SYNTHETIC_OPC_HEX + '"}\n')
    assert find_sentinels(scratch.read_text()) == [SYNTHETIC_OPC_HEX]
    scratch.write_text('{"event": "line.activate.created"}\n')
    assert find_sentinels(scratch.read_text()) == []
