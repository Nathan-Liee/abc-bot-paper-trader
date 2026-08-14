"""Exporter directory handling: behavior and static parity tests.

The MQL5 exporter has no headless runner, so the required behaviors
(missing/existing directory, successful open, append/write, bounded
reopen after failure, corruption preservation) are exercised against a
real filesystem sandbox through ``RefExporter``, a Python mirror of the
CJsonExporter algorithm in JsonExporter.mqh. Static tests pin the .mqh
to the same properties (FolderCreate before FileOpen, idempotency,
explicit errors, preserved transport guarantees).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO

import pytest

from collector.settings import PROJECT_ROOT

EXPORTER = PROJECT_ROOT / "mql5-bridge" / "src" / "Export" / "JsonExporter.mqh"

DEFAULT_PATH = "data\\raw\\mql5_bridge_events.jsonl"
LINE = '{"event_type":"TICK_RECEIVED","source":"mql5","ts_bridge":"2026-08-14T09:00:00Z"}'


class ExporterError(Exception):
    """Mirror of a failed MQL5 directory creation / file operation."""


class RefExporter:
    """Python mirror of the CJsonExporter algorithm.

    normalize path -> ensure directory (idempotent, segment-wise) ->
    open read/write at EOF -> append; on lost handle, bounded reopen
    with corruption preservation (target renamed to *.corrupted.* and a
    fresh file started).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = ""
        self.handle: BinaryIO | None = None
        self.error_count = 0
        self.reopen_attempts = 0
        self.max_reopen_attempts = 3
        self.corrupt_renamed = False

    @staticmethod
    def normalize_path(path: str) -> str:
        return path.replace("/", "\\").lstrip("\\")

    @staticmethod
    def directory_of(path: str) -> str:
        sep = path.rfind("\\")
        return "" if sep < 0 else path[:sep]

    def _target(self, path: str) -> Path:
        return self.root.joinpath(*path.split("\\"))

    def ensure_directory(self, dir_path: str) -> None:
        if not dir_path:
            return
        acc = ""
        for segment in dir_path.split("\\"):
            if not segment:
                continue
            acc = f"{acc}\\{segment}" if acc else segment
            try:
                self._target(acc).mkdir()
            except FileExistsError:
                continue
            except OSError as exc:
                raise ExporterError(f"cannot create directory '{acc}': {exc}") from exc

    def open_append(self, path: str) -> bool:
        try:
            self.ensure_directory(self.directory_of(path))
            self.handle = self._target(path).open("a+b")
            return True
        except (OSError, ExporterError):
            self.handle = None
            return False

    def open(self, path: str, max_attempts: int) -> bool:
        self.path = self.normalize_path(path)
        if not self.path:
            return False
        self.max_reopen_attempts = max_attempts
        return self.open_append(self.path)

    def append_line(self, line: str) -> bool:
        if self.handle is None:
            if not self.reopen_after_failure():
                return False
        assert self.handle is not None
        try:
            self.handle.write((line + "\n").encode("ascii"))
            self.handle.flush()  # readback visibility (MQL5 FileWriteString)
            self.reopen_attempts = 0
            return True
        except (OSError, ValueError):
            self.error_count += 1
            self.reopen_attempts = 0
            return False

    def reopen_after_failure(self) -> bool:
        if self.reopen_attempts >= self.max_reopen_attempts:
            return False
        self.reopen_attempts += 1
        if self.open_append(self.path):
            return True
        if not self.corrupt_renamed:
            backup = self.path + ".corrupted.20260814"
            try:
                os.rename(self._target(self.path), self._target(backup))
            except OSError:
                return False
            self.corrupt_renamed = True
            self.reopen_attempts = 0
            return self.open_append(self.path)
        return False

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


def _target(root: Path) -> Path:
    return root.joinpath(*DEFAULT_PATH.split("\\"))


def test_open_creates_missing_directory(root: Path) -> None:
    assert not _target(root).exists()
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    assert _target(root).exists()
    assert exporter.append_line(LINE) is True
    assert _target(root).read_text(encoding="ascii") == LINE + "\n"


def test_open_with_existing_directory_is_idempotent(root: Path) -> None:
    _target(root).parent.mkdir(parents=True)
    assert RefExporter(root).open(DEFAULT_PATH, 3) is True
    assert RefExporter(root).open(DEFAULT_PATH, 3) is True
    assert RefExporter(root).open(DEFAULT_PATH, 3) is True
    assert _target(root).exists()


def test_successful_open_and_append_only(root: Path) -> None:
    _target(root).parent.mkdir(parents=True)
    _target(root).write_text('{"prev":1}\n', encoding="ascii")
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    assert exporter.append_line(LINE) is True
    assert _target(root).read_text(encoding="ascii") == '{"prev":1}\n' + LINE + "\n"


def test_write_failure_increments_error_count(root: Path) -> None:
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    os.close(exporter.handle.fileno())  # invalidate the file descriptor
    assert exporter.append_line(LINE) is False
    assert exporter.error_count == 1


def test_reopen_after_failure_recovers_and_appends(root: Path) -> None:
    _target(root).parent.mkdir(parents=True)
    _target(root).write_text(LINE + "\n", encoding="ascii")
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    exporter.close()
    exporter.handle = None  # lost handle -> next append reopens
    assert exporter.append_line(LINE) is True
    assert _target(root).read_text(encoding="ascii") == LINE + "\n" + LINE + "\n"
    assert exporter.error_count == 0


def test_reopen_retries_are_bounded(root: Path) -> None:
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    exporter.close()
    shutil.rmtree(root)  # sandbox gone -> every open fails
    for _ in range(6):
        assert exporter.append_line(LINE) is False
    assert exporter.reopen_attempts == 3
    assert exporter.error_count == 0


def test_corrupt_target_renamed_and_fresh_file_started(root: Path) -> None:
    exporter = RefExporter(root)
    assert exporter.open(DEFAULT_PATH, 3) is True
    exporter.close()
    _target(root).unlink()
    _target(root).mkdir()  # target now unopenable (open fails)
    exporter.handle = None
    assert exporter.append_line(LINE) is True
    assert exporter.corrupt_renamed is True
    backup = _target(root).parent / "mql5_bridge_events.jsonl.corrupted.20260814"
    assert backup.is_dir()
    assert _target(root).read_text(encoding="ascii") == LINE + "\n"


def _exporter_text() -> str:
    return EXPORTER.read_text(encoding="utf-8")


def test_mqh_creates_directory_before_opening_file() -> None:
    text = _exporter_text()
    assert text.index("bool EnsureDirectory") < text.index("int OpenAppend(")
    body = text[text.index("int OpenAppend(") :]
    assert body.index("EnsureDirectory(DirectoryOf") < body.index("FileOpen")


def test_mqh_directory_creation_is_idempotent_and_explicit() -> None:
    text = _exporter_text()
    assert "EnsureDirectory" in text
    assert "FolderCreate(acc)" in text
    assert "GetLastError() != 0" in text
    assert "cannot create directory" in text
    assert "StringSplit" in text  # directory part derived from the path


def test_mqh_preserves_transport_guarantees() -> None:
    text = _exporter_text()
    assert "FILE_READ | FILE_WRITE" in text  # append-only open
    assert "BRIDGE_EXPORTER_CP_UTF8" in text  # UTF-8 output
    assert "SEEK_END" in text  # seek to end on every open
    assert "m_maxReopenAttempts" in text  # bounded reopen retries
    assert "FileMove" in text  # corruption preservation
    assert ".corrupted." in text


def test_mqh_path_stays_relative_to_mql5_files() -> None:
    text = _exporter_text()
    assert "FILE_COMMON" not in text
    assert "NormalizePath" in text
