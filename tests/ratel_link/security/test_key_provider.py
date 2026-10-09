import base64
import os
import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from ratel_link.config import Settings
from ratel_link.main import create_app
from ratel_link.security.crypto import encrypt_field
from ratel_link.security.key_provider import (
    KEY_BYTES,
    FileKeyProvider,
    KeyFileError,
    KeyFileMissingError,
    KeyUnavailableError,
    NoKeyProvider,
    build_key_provider,
    read_key_file,
    write_new_key_file,
)
from tests.synthetic import SYNTHETIC_IMSI

# Looks like key material, is not one. Used to prove error messages never echo file contents.
JUNK_CONTENT = "SENTINEL-KEY-FILE-CONTENT-DO-NOT-LOG"


def _key_file(tmp_path: Path, mode: int = 0o600, content: bytes | None = None) -> Path:
    path = tmp_path / "ratel_link.key"
    raw = content if content is not None else base64.b64encode(os.urandom(KEY_BYTES)) + b"\n"
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _settings(env: str, key_file: Path | None, key_id: str = "1") -> Settings:
    return Settings(ratel_env=env, ratel_link_key_file=key_file, ratel_link_key_id=key_id)


# --- the file -----------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [0o600, 0o400], ids=oct)
def test_owner_only_file_is_accepted(tmp_path: Path, mode: int) -> None:
    assert len(read_key_file(_key_file(tmp_path, mode))) == KEY_BYTES


def test_trailing_newline_is_optional(tmp_path: Path) -> None:
    raw = base64.b64encode(os.urandom(KEY_BYTES))
    assert len(read_key_file(_key_file(tmp_path, content=raw))) == KEY_BYTES


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o666, 0o601], ids=oct)
def test_group_or_other_access_is_rejected(tmp_path: Path, mode: int) -> None:
    path = _key_file(tmp_path, mode)
    with pytest.raises(KeyFileError) as exc:
        read_key_file(path)
    assert str(path) in str(exc.value)
    assert "owner-only" in str(exc.value)


def test_file_owned_by_someone_else_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Cannot chown without root, so pretend this process runs as a different user.
    path = _key_file(tmp_path)
    monkeypatch.setattr(os, "geteuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(KeyFileError, match="not owned by the user"):
        read_key_file(path)


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(KeyFileError):
        read_key_file(tmp_path)


def test_symlink_is_rejected(tmp_path: Path) -> None:
    target = _key_file(tmp_path)
    link = tmp_path / "link.key"
    link.symlink_to(target)
    with pytest.raises(KeyFileError):
        read_key_file(link)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_named_pipe_is_rejected_without_blocking(tmp_path: Path) -> None:
    pipe = tmp_path / "pipe.key"
    os.mkfifo(pipe)  # opening this for reading would block forever without O_NONBLOCK
    with pytest.raises(KeyFileError, match="not a regular file"):
        read_key_file(pipe)


def test_missing_file_is_reported_as_missing(tmp_path: Path) -> None:
    with pytest.raises(KeyFileMissingError, match="does not exist"):
        read_key_file(tmp_path / "nope.key")


@pytest.mark.parametrize(
    "content",
    [
        b"",
        JUNK_CONTENT.encode(),
        base64.b64encode(os.urandom(16)),  # a valid AES-128 key is still the wrong size
        base64.b64encode(os.urandom(33)),
        base64.b64encode(os.urandom(KEY_BYTES)) + b"\nextra",
        b"A" * 5000,
    ],
)
def test_malformed_content_is_rejected_without_echoing_it(tmp_path: Path, content: bytes) -> None:
    path = _key_file(tmp_path, content=content)
    with pytest.raises(KeyFileError) as exc:
        read_key_file(path)
    message = str(exc.value)
    assert str(path) in message
    assert "32 bytes" in message
    assert JUNK_CONTENT not in message
    if content:
        assert content.decode(errors="replace")[:20] not in message


# --- the provider -------------------------------------------------------------------------------


def test_provider_serves_its_key_and_refuses_other_ids(tmp_path: Path) -> None:
    provider = FileKeyProvider(_key_file(tmp_path), "3")
    assert provider.current_key_id() == "3"
    assert len(provider.get_key("3")) == KEY_BYTES
    with pytest.raises(KeyUnavailableError):
        provider.get_key("4")


def test_provider_repr_and_str_hide_the_key(tmp_path: Path) -> None:
    raw = os.urandom(KEY_BYTES)
    path = _key_file(tmp_path, content=base64.b64encode(raw))
    provider = FileKeyProvider(path, "1")
    for text in (repr(provider), str(provider), f"{provider}", f"{provider!r}"):
        assert base64.b64encode(raw).decode() not in text
        assert repr(raw) not in text
        assert raw.hex() not in text


def test_provider_does_not_reread_the_file(tmp_path: Path) -> None:
    path = _key_file(tmp_path)
    provider = FileKeyProvider(path, "1")
    first = provider.get_key("1")
    path.unlink()
    assert provider.get_key("1") == first


# --- generating a key ---------------------------------------------------------------------------


def test_new_key_file_is_valid_owner_only_and_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "new.key"
    write_new_key_file(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(read_key_file(path)) == KEY_BYTES
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_new_key_file(path)
    assert path.read_bytes() == before


def test_new_key_files_differ(tmp_path: Path) -> None:
    write_new_key_file(tmp_path / "a.key")
    write_new_key_file(tmp_path / "b.key")
    assert read_key_file(tmp_path / "a.key") != read_key_file(tmp_path / "b.key")


def test_new_key_file_is_owner_only_even_with_a_permissive_umask(tmp_path: Path) -> None:
    old = os.umask(0)
    try:
        write_new_key_file(tmp_path / "new.key")
    finally:
        os.umask(old)
    assert stat.S_IMODE((tmp_path / "new.key").stat().st_mode) == 0o600


# --- startup rule -------------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_no_key_file_configured_stops_startup_outside_local(env: str) -> None:
    with pytest.raises(KeyFileError, match="RATEL_LINK_KEY_FILE"):
        create_app(_settings(env, None))


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_missing_key_file_stops_startup_outside_local(env: str, tmp_path: Path) -> None:
    with pytest.raises(KeyFileMissingError):
        create_app(_settings(env, tmp_path / "nope.key"))


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_unsafe_key_file_stops_startup_outside_local(env: str, tmp_path: Path) -> None:
    with pytest.raises(KeyFileError, match="owner-only"):
        create_app(_settings(env, _key_file(tmp_path, 0o644)))


@pytest.mark.parametrize("env", ["lab", "staging", "production"])
def test_valid_key_file_starts_outside_local(env: str, tmp_path: Path) -> None:
    app = create_app(_settings(env, _key_file(tmp_path)))
    assert isinstance(app.state.key_provider, FileKeyProvider)


@pytest.mark.parametrize("env", ["local", "test"])
@pytest.mark.parametrize("missing", [True, False])
def test_local_and_test_start_without_a_key_but_cannot_encrypt(
    env: str, missing: bool, tmp_path: Path
) -> None:
    app = create_app(_settings(env, tmp_path / "nope.key" if missing else None))
    provider = app.state.key_provider
    assert isinstance(provider, NoKeyProvider)
    with pytest.raises(KeyUnavailableError):
        encrypt_field(provider, SYNTHETIC_IMSI, "ki", b"x")


@pytest.mark.parametrize("env", ["local", "test"])
def test_an_unsafe_key_file_stops_startup_in_every_environment(env: str, tmp_path: Path) -> None:
    with pytest.raises(KeyFileError, match="owner-only"):
        create_app(_settings(env, _key_file(tmp_path, 0o644)))


def test_build_provider_uses_the_configured_key_id(tmp_path: Path) -> None:
    provider = build_key_provider(_settings("lab", _key_file(tmp_path), key_id="2026-10"))
    assert provider.current_key_id() == "2026-10"


# --- settings -----------------------------------------------------------------------------------


@pytest.mark.parametrize("kid", ["", "A", "-1", "has space", "a|b", "x" * 33, "ключ"])
def test_bad_key_id_is_rejected(kid: str) -> None:
    with pytest.raises(ValidationError):
        Settings(ratel_link_key_id=kid)


def test_key_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RATEL_LINK_KEY_FILE", str(tmp_path / "k"))
    monkeypatch.setenv("RATEL_LINK_KEY_ID", "5")
    s = Settings()
    assert s.ratel_link_key_file == tmp_path / "k"
    assert s.ratel_link_key_id == "5"


@pytest.mark.parametrize(
    "field", ["ratel_link_api_key_max_age_days", "ratel_link_api_key_expiry_warn_days"]
)
@pytest.mark.parametrize("value", [91, 365, 0, -1])
def test_api_key_ages_outside_the_build_plan_cap_are_rejected(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_ninety_days_is_the_largest_allowed_key_lifetime() -> None:
    assert Settings(ratel_link_api_key_max_age_days=90).ratel_link_api_key_max_age_days == 90


@pytest.mark.parametrize("value", [0, 31, -3])
def test_overlap_is_bounded(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(ratel_link_api_key_rotation_overlap_days=value)


def test_overlap_longer_than_the_key_lifetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(ratel_link_api_key_max_age_days=5, ratel_link_api_key_rotation_overlap_days=6)


def test_api_key_defaults() -> None:
    s = Settings()
    assert (
        s.ratel_link_api_key_max_age_days,
        s.ratel_link_api_key_rotation_overlap_days,
        s.ratel_link_api_key_expiry_warn_days,
    ) == (90, 7, 14)
