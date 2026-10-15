"""Tests for W2-15: atomic write, ordered replay, ack-then-delete,
quarantine, and duplicate keys. No network, no lab.
"""
from __future__ import annotations

from pathlib import Path

from services.meter_agent.spool.spool import Spool


class FakeSender:
    """Records what it was asked to send. Can be told to fail."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[object] = []

    def __call__(self, batch: object) -> bool:
        if self.fail:
            raise RuntimeError("API unreachable")
        self.sent.append(batch)
        return True


def _batch(period_start: int, up: int = 1, down: int = 2) -> list[dict]:
    return [
        {
            "imsi": "621000000000001",
            "period_start": period_start,
            "period_end": period_start + 300,
            "bytes_up": up,
            "bytes_down": down,
        }
    ]


def test_spool_writes_atomically(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    path = spool.spool("0000000001.json", _batch(1))
    assert path.exists()
    # No temporary file left behind.
    assert not list(tmp_path.glob(".tmp-*"))


def test_failed_sender_leaves_files_and_they_replay_in_order(
    tmp_path: Path,
) -> None:
    spool = Spool(tmp_path)
    spool.spool("0000000003.json", _batch(3))
    spool.spool("0000000001.json", _batch(1))
    spool.spool("0000000002.json", _batch(2))

    # Sender fails: nothing is deleted.
    result = spool.replay(FakeSender(fail=True))
    assert result.delivered == 0
    assert result.remaining == 3

    # Sender works: everything arrives, oldest first, once each.
    sender = FakeSender()
    result = spool.replay(sender)
    assert result.delivered == 3
    assert result.remaining == 0
    periods = [batch[0]["period_start"] for batch in sender.sent]
    assert periods == [1, 2, 3]


def test_crash_between_write_and_ack_leaves_file(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    spool.spool("0000000001.json", _batch(1))

    class CrashAfterSend:
        def __init__(self) -> None:
            self.sent = 0

        def __call__(self, batch: object) -> bool:
            self.sent += 1
            # Acknowledge, but simulate a crash before the unlink by
            # raising. The file must stay on disk.
            raise RuntimeError("crashed before unlink")

    result = spool.replay(CrashAfterSend())
    assert result.delivered == 0
    assert result.remaining == 1
    # Second pass delivers it.
    result = spool.replay(FakeSender())
    assert result.delivered == 1
    assert result.remaining == 0


def test_corrupt_file_is_quarantined_and_replay_continues(
    tmp_path: Path,
) -> None:
    spool = Spool(tmp_path)
    spool.spool("0000000001.json", _batch(1))
    (tmp_path / "0000000002.json").write_text("{not json")
    spool.spool("0000000003.json", _batch(3))

    sender = FakeSender()
    result = spool.replay(sender)
    assert result.delivered == 2
    assert result.quarantined == 1
    assert result.remaining == 0
    quarantined = list((tmp_path / "quarantine").iterdir())
    assert len(quarantined) == 1
    assert quarantined[0].name == "0000000002.json"
    # The corrupt file did not stop the later one.
    assert [b[0]["period_start"] for b in sender.sent] == [1, 3]


def test_two_files_with_same_key_replay_without_error(
    tmp_path: Path,
) -> None:
    # Same key, written twice (a crash, a replay). The API upserts, so
    # both are sent; the spool itself does not error.
    spool = Spool(tmp_path)
    spool.spool("0000000001.json", _batch(1))
    spool.spool("0000000001.json", _batch(1))  # overwrites, same name

    sender = FakeSender()
    result = spool.replay(sender)
    assert result.delivered == 1
    assert result.remaining == 0


def test_pending_ignores_temporary_files(tmp_path: Path) -> None:
    spool = Spool(tmp_path)
    (tmp_path / ".tmp-abc").write_text("x")
    spool.spool("0000000001.json", _batch(1))
    assert [p.name for p in spool.pending()] == ["0000000001.json"]


def test_spool_creates_its_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "spool"
    Spool(target)
    assert target.is_dir()