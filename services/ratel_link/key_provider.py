"""Where RatelLink's Ki/OPc encryption key comes from (docs/adr/0006).

All encryption code depends on the `KeyProvider` interface only, so the file-based provider
below can be replaced by a secret manager or KMS later without touching the crypto.

There is never a default or fallback key. If no key is available, encrypting and decrypting
raise `KeyUnavailableError`. Nothing in this module puts key bytes in an exception, a log line
or a repr.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import stat
from pathlib import Path
from typing import Protocol

from common.logging import log_event
from ratel_link.config import Settings

log = logging.getLogger("ratel.link.keys")

KEY_BYTES = 32  # AES-256
_MAX_KEY_FILE_BYTES = 1024
_NO_FOLLOW = getattr(os, "O_NOFOLLOW", 0)
# Without O_NONBLOCK, opening a named pipe blocks until a writer appears and startup would hang.
_OPEN_FLAGS = os.O_RDONLY | _NO_FOLLOW | os.O_NONBLOCK
_LOCAL_ENVIRONMENTS = {"local", "test"}


class KeyUnavailableError(Exception):
    """No usable key for this request. Callers must fail closed, never continue unencrypted."""


class KeyFileError(Exception):
    """The key file is missing, unsafe or malformed. At startup this stops the service."""


class KeyFileMissingError(KeyFileError):
    """The configured key file does not exist."""


class KeyProvider(Protocol):
    def current_key_id(self) -> str:
        """Id of the key used for new encryptions."""
        ...

    def get_key(self, kid: str) -> bytes:
        """The 32-byte key with this id. Raises KeyUnavailableError if there is none."""
        ...


def read_key_file(path: Path) -> bytes:
    """Read and validate a key file: base64 text holding exactly 32 bytes.

    The file must be a regular file (not a symlink), owned by this process's user, with no group or
    other permission bits. Checks run on the opened descriptor, so the file cannot change between
    the check and the read. Errors name the path and the problem, never the contents.
    """
    try:
        fd = os.open(path, _OPEN_FLAGS)
    except FileNotFoundError:
        raise KeyFileMissingError(f"key file {path} does not exist") from None
    except OSError as exc:
        raise KeyFileError(f"key file {path} cannot be opened: {exc.strerror}") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise KeyFileError(f"key file {path} is not a regular file")
        if info.st_uid != os.geteuid():
            raise KeyFileError(f"key file {path} is not owned by the user running RatelLink")
        if info.st_mode & 0o077:
            raise KeyFileError(
                f"key file {path} is accessible to group or others (mode "
                f"{info.st_mode & 0o777:03o}); it must be owner-only, for example chmod 600"
            )
        data = os.read(fd, _MAX_KEY_FILE_BYTES + 1)
    finally:
        os.close(fd)
    return _decode_key(path, data)


def _decode_key(path: Path, data: bytes) -> bytes:
    problem = KeyFileError(f"key file {path} must contain base64 of exactly {KEY_BYTES} bytes")
    if len(data) > _MAX_KEY_FILE_BYTES:
        raise problem
    try:
        key = base64.b64decode(data.strip(), validate=True)
    except binascii.Error:
        raise problem from None
    if len(key) != KEY_BYTES:
        raise problem
    return key


def write_new_key_file(path: Path) -> None:
    """Create a key file with 32 random bytes. Refuses to overwrite. Prints and returns nothing."""
    key = os.urandom(KEY_BYTES)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NO_FOLLOW, 0o600)  # FileExistsError
    try:
        os.fchmod(fd, 0o600)  # not left to the umask
        os.write(fd, base64.b64encode(key) + b"\n")
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    os.close(fd)


class FileKeyProvider:
    """One key, read once at startup from an owner-only file. Other key ids are unknown."""

    def __init__(self, path: Path, key_id: str) -> None:
        self._key = read_key_file(path)
        self._key_id = key_id

    def current_key_id(self) -> str:
        return self._key_id

    def get_key(self, kid: str) -> bytes:
        if kid != self._key_id:
            raise KeyUnavailableError("no key with that id is configured")
        return self._key

    def __repr__(self) -> str:
        return f"FileKeyProvider(key_id={self._key_id!r})"


class NoKeyProvider:
    """Local and test only: the app starts, but every encrypt or decrypt fails."""

    def current_key_id(self) -> str:
        raise KeyUnavailableError("no encryption key is configured")

    def get_key(self, kid: str) -> bytes:
        raise KeyUnavailableError("no encryption key is configured")

    def __repr__(self) -> str:
        return "NoKeyProvider()"


def build_key_provider(settings: Settings) -> KeyProvider:
    """The startup rule. Outside local and test, no usable key file means no service.

    A key file that exists but is unsafe or malformed stops startup in every environment.
    """
    local = settings.ratel_env in _LOCAL_ENVIRONMENTS
    if settings.ratel_link_key_file is None:
        if not local:
            raise KeyFileError("RATEL_LINK_KEY_FILE is not set; it is required outside local/test")
        log_event(log, logging.WARNING, "key.provider.none", reason="not_configured")
        return NoKeyProvider()
    try:
        return FileKeyProvider(settings.ratel_link_key_file, settings.ratel_link_key_id)
    except KeyFileMissingError:
        if not local:
            raise
        log_event(log, logging.WARNING, "key.provider.none", reason="file_missing")
        return NoKeyProvider()
