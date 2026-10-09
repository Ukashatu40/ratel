import io
import logging
import re
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from ratel_link import admin_cli
from ratel_link.admin_cli import Services, build_parser, main, run
from ratel_link.security.key_provider import read_key_file
from ratel_link.services.api_key_admin import KeyPolicy
from ratel_link.services.authentication import ApiPrincipal, authenticate
from tests.ratel_link.fakes import FakeClock, InMemoryApiKeyRepository

TOKEN_RE = re.compile(r"rlk_[a-z][a-z0-9-]{2,31}\.[A-Za-z0-9_-]{43}")


class Harness:
    def __init__(self) -> None:
        self.repo = InMemoryApiKeyRepository()
        self.clock = FakeClock()
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.index_calls = 0
        self.services = Services(
            api_keys=self.repo,
            policy=KeyPolicy(),
            now=self.clock,
            create_indexes=self._indexes,
            out=self.out,
            err=self.err,
        )

    def _indexes(self) -> list[str]:
        self.index_calls += 1
        return ["sim_key.imsi", "api_key.api_key_id"]

    def cli(self, *argv: str) -> int:
        self.out.seek(0)
        self.out.truncate()
        self.err.seek(0)
        self.err.truncate()
        return run(build_parser().parse_args(argv), self.services)

    def token(self) -> str:
        found = TOKEN_RE.findall(self.out.getvalue())
        assert len(found) == 1
        return found[0]


def test_create_prints_the_key_once_on_stdout_and_a_reminder_on_stderr() -> None:
    h = Harness()
    assert h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS") == 0
    token = h.token()
    assert h.out.getvalue() == token + "\n"  # nothing else on stdout
    assert token not in h.err.getvalue()  # the reminder never repeats the key
    assert "owner-only" in h.err.getvalue() and "cannot be shown again" in h.err.getvalue()
    assert authenticate(f"Bearer {token}", h.repo, h.clock()) == ApiPrincipal("bss-app", 1)


def test_create_refuses_a_duplicate_and_prints_no_key() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    assert h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS") == 1
    assert h.out.getvalue() == ""
    assert "already exists" in h.err.getvalue()


def test_rotate_prints_the_new_key_and_both_work_during_the_overlap() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    old = h.token()
    assert h.cli("api-key", "rotate", "--id", "bss-app") == 0
    new = h.token()
    assert new != old
    assert "generation=2" in h.err.getvalue()
    for token, generation in ((old, 1), (new, 2)):
        result = authenticate(f"Bearer {token}", h.repo, h.clock())
        assert result == ApiPrincipal("bss-app", generation)
    h.clock.advance(days=8)
    assert not isinstance(authenticate(f"Bearer {old}", h.repo, h.clock()), ApiPrincipal)


def test_third_key_is_refused_with_no_output_on_stdout() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    h.cli("api-key", "rotate", "--id", "bss-app")
    assert h.cli("api-key", "rotate", "--id", "bss-app") == 1
    assert h.out.getvalue() == ""
    assert "two valid keys" in h.err.getvalue()


def test_revoke_and_disable() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    token = h.token()
    assert h.cli("api-key", "revoke", "--id", "bss-app", "--generation", "1") == 0
    assert not isinstance(authenticate(f"Bearer {token}", h.repo, h.clock()), ApiPrincipal)
    assert h.cli("api-key", "disable", "--id", "bss-app") == 0
    assert h.repo.documents["bss-app"]["status"] == "disabled"


def test_unknown_system_or_generation_is_an_error_not_a_crash() -> None:
    h = Harness()
    assert h.cli("api-key", "rotate", "--id", "nobody") == 1
    assert h.cli("api-key", "revoke", "--id", "nobody", "--generation", "1") == 1
    assert h.cli("api-key", "disable", "--id", "nobody") == 1
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    assert h.cli("api-key", "revoke", "--id", "bss-app", "--generation", "7") == 1
    assert "no generation 7" in h.err.getvalue()


def test_list_shows_lifetimes_and_never_a_key_or_a_hash() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    token = h.token()
    h.cli("api-key", "rotate", "--id", "bss-app")
    h.cli("api-key", "create", "--id", "meter-agent", "--name", "RatelMeter agent")
    h.cli("api-key", "revoke", "--id", "meter-agent", "--generation", "1")
    assert h.cli("api-key", "list") == 0
    text = h.out.getvalue()
    assert "bss-app  RatelBSS  active" in text
    assert "meter-agent" in text
    assert "valid" in text and "revoked" in text
    assert "generation 1" in text and "generation 2" in text
    assert token not in text and token.split(".", 1)[1] not in text
    assert not TOKEN_RE.search(text)
    for doc in h.repo.documents.values():
        for g in doc["generations"]:
            assert g["secret_hash"] not in text
    assert not re.search(r"[0-9a-f]{64}", text)


def test_list_marks_expired_keys() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    h.clock.advance(days=91)
    h.cli("api-key", "list")
    assert "expired" in h.out.getvalue()


def test_check_expiry_logs_events_and_summarises_on_stderr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    token = h.token()
    h.clock.advance(days=80)
    caplog.set_level(logging.INFO)
    assert h.cli("api-key", "check-expiry") == 0
    assert "1 key(s) expire within 14 days" in h.err.getvalue()
    assert [
        r.__dict__["days_left"]
        for r in caplog.records
        if r.__dict__.get("event") == "api_key.expiring"
    ] == [10]
    assert token not in caplog.text and token.split(".", 1)[1] not in caplog.text


def test_no_token_ever_reaches_the_logging_system(caplog: pytest.LogCaptureFixture) -> None:
    h = Harness()
    caplog.set_level(logging.DEBUG)
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    first = h.token()
    h.cli("api-key", "rotate", "--id", "bss-app")
    second = h.token()
    for token in (first, second):
        assert token not in caplog.text
        assert token.split(".", 1)[1] not in caplog.text


def test_init_db_runs_the_index_creation() -> None:
    h = Harness()
    assert h.cli("init-db") == 0
    assert h.index_calls == 1
    assert "index ready: sim_key.imsi" in h.out.getvalue()


def test_no_option_accepts_a_key_or_a_secret() -> None:
    options: set[str] = set()

    def walk(parser: object) -> None:
        for action in getattr(parser, "_actions", []):
            options.update(o for o in action.option_strings if o.startswith("--"))
            for sub in getattr(action, "choices", None) or {}:
                child = action.choices[sub] if isinstance(action.choices, dict) else None
                if child is not None:
                    walk(child)

    walk(build_parser())
    assert options == {"--help", "--id", "--name", "--generation", "--out"}


# --- key generate (needs no database) -----------------------------------------------------------


def test_key_generate_writes_a_valid_owner_only_file_and_prints_no_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "ratel_link.key"
    assert main(["key", "generate", "--out", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(path) in captured.err
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    key = read_key_file(path)
    text = path.read_text().strip()
    assert text not in captured.err and key.hex() not in captured.err
    assert "offline" in captured.err


def test_key_generate_refuses_to_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "ratel_link.key"
    path.write_text("existing")
    assert main(["key", "generate", "--out", str(path)]) == 1
    assert path.read_text() == "existing"
    assert "Refusing to overwrite" in capsys.readouterr().err


def test_key_generate_reports_a_missing_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["key", "generate", "--out", str(tmp_path / "nope" / "k")]) == 1
    assert "cannot write" in capsys.readouterr().err


def test_invalid_configuration_names_fields_without_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://user:hunter2@192.0.2.9:27017")
    monkeypatch.setenv("RATEL_LINK_API_KEY_MAX_AGE_DAYS", "365")
    assert main(["api-key", "list"]) == 2
    err = capsys.readouterr().err
    assert "mongo_uri" in err and "ratel_link_api_key_max_age_days" in err
    assert "hunter2" not in err and "192.0.2.9" not in err


def test_database_failure_prints_the_error_type_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pymongo.errors import ServerSelectionTimeoutError

    class Boom:
        def list_all(self) -> None:
            raise ServerSelectionTimeoutError("secret-host:27017 password=hunter2")

    class FakeDatabase:
        class client:
            @staticmethod
            def close() -> None: ...

    monkeypatch.setattr(admin_cli, "open_database", lambda _s: FakeDatabase())
    monkeypatch.setattr(admin_cli, "MongoApiKeyRepository", lambda _d: Boom())
    assert main(["api-key", "list"]) == 1
    err = capsys.readouterr().err
    assert "ServerSelectionTimeoutError" in err
    assert "hunter2" not in err and "secret-host" not in err


def test_timestamps_in_list_are_utc_iso() -> None:
    h = Harness()
    h.cli("api-key", "create", "--id", "bss-app", "--name", "RatelBSS")
    h.cli("api-key", "list")
    expected = (h.clock() + timedelta(days=90)).isoformat(timespec="seconds")
    assert expected in h.out.getvalue()
    assert expected.endswith("+00:00")


def test_stdout_carries_only_the_key_even_with_real_logging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # main() configures JSON logging. Its lines must go to stderr so `KEY=$(admin_cli ...)`
    # captures the key and nothing else.
    repo = InMemoryApiKeyRepository()

    class FakeDatabase:
        class client:
            @staticmethod
            def close() -> None: ...

    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    monkeypatch.setattr(admin_cli, "open_database", lambda _s: FakeDatabase())
    monkeypatch.setattr(admin_cli, "MongoApiKeyRepository", lambda _d: repo)
    try:
        assert main(["api-key", "create", "--id", "bss-app", "--name", "RatelBSS"]) == 0
    finally:
        root.handlers[:], root.level = saved, level
    captured = capsys.readouterr()
    assert TOKEN_RE.fullmatch(captured.out.strip())
    assert captured.out.count("\n") == 1
    assert "api_key.created" in captured.err
    assert captured.out.strip() not in captured.err
