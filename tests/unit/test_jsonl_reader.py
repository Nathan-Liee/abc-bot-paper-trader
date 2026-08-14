"""Incremental JSONL reader tests: framing, offsets, rotation, resumption."""

from __future__ import annotations

from pathlib import Path

from collector.adapters.reader import JsonlFileReader

L1 = b'{"a": 1}'
L2 = b'{"b": 2}'
L3 = b'{"c": 3}'


def _write(path: Path, data: bytes) -> None:
    with path.open("ab") as fh:
        fh.write(data)


def test_empty_file_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"")
    reader = JsonlFileReader(path)
    poll = reader.poll()
    assert poll.lines == ()
    assert poll.unavailable is False
    assert poll.rotation is False


def test_missing_file_is_unavailable(tmp_path: Path) -> None:
    reader = JsonlFileReader(tmp_path / "nope.jsonl")
    poll = reader.poll()
    assert poll.unavailable is True
    assert poll.lines == ()


def test_reads_complete_lines_with_offsets(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n" + L2 + b"\n")
    reader = JsonlFileReader(path)
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [L1, L2]
    assert poll.lines[0].start_offset == 0
    assert poll.lines[1].start_offset == len(L1) + 1
    assert poll.offset == len(L1) + 1 + len(L2) + 1


def test_incremental_append_is_read_incrementally(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n")
    reader = JsonlFileReader(path)
    first = reader.poll()
    assert [line.data for line in first.lines] == [L1]
    assert first.reads <= len(L1) + 1

    _write(path, L2 + b"\n" + L3 + b"\n")
    second = reader.poll()
    assert [line.data for line in second.lines] == [L2, L3]
    assert second.reads == len(L2) + 1 + len(L3) + 1
    assert reader.offset == len(L1) + 1 + len(L2) + 1 + len(L3) + 1


def test_holds_partial_line_until_terminator(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n" + L2[:3])
    reader = JsonlFileReader(path)
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [L1]
    assert poll.held_partial is True
    assert poll.offset == len(L1) + 1

    _write(path, L2[3:] + b"\n")
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [L2]
    assert poll.held_partial is False
    assert poll.offset == len(L1) + 1 + len(L2) + 1


def test_eof_no_newline_holds_until_growth(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1)
    reader = JsonlFileReader(path)
    poll = reader.poll()
    assert poll.lines == ()
    assert poll.held_partial is True
    _write(path, b"\n")
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [L1]


def test_resumes_from_cursor_offset(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n" + L2 + b"\n" + L3 + b"\n")
    reader = JsonlFileReader(path, start_offset=len(L1) + 1)
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [L2, L3]
    assert poll.offset == len(L1) + 1 + len(L2) + 1 + len(L3) + 1


def test_replacement_file_detects_rotation(tmp_path: Path) -> None:
    """The bridge rotates by renaming the corrupt file and writing fresh."""
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n")
    reader = JsonlFileReader(path)
    reader.poll()

    path.rename(tmp_path / "events.jsonl.corrupt")
    _write(path, L3 + b"\n")
    poll = reader.poll()
    assert poll.rotation is True
    # The fresh stream is read from offset zero (partial state dropped).
    assert [line.data for line in poll.lines] == [L3]
    assert reader.offset == len(L3) + 1


def test_shrink_below_cursor_detects_rotation(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n" + L2 + b"\n")
    reader = JsonlFileReader(path, start_offset=len(L1) + 1 + len(L2) + 1)
    reader.poll()

    path.write_bytes(L3 + b"\n")
    poll = reader.poll()
    assert poll.rotation is True
    assert [line.data for line in poll.lines] == [L3]


def test_rotation_drops_held_partial(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n" + L2[:2])
    reader = JsonlFileReader(path)
    reader.poll()

    path.rename(tmp_path / "events.jsonl.corrupt")
    _write(path, L3 + b"\n")
    poll = reader.poll()
    assert poll.rotation is True
    assert [line.data for line in poll.lines] == [L3]
    assert poll.held_partial is False


def test_unavailable_after_first_poll(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n")
    reader = JsonlFileReader(path)
    reader.poll()
    path.unlink()
    poll = reader.poll()
    assert poll.unavailable is True


def test_recreate_after_unlink_is_new_stream(tmp_path: Path) -> None:
    """A fresh file at the same path is a new stream: rotation, not tail."""
    path = tmp_path / "events.jsonl"
    _write(path, L1 + b"\n")
    reader = JsonlFileReader(path)
    reader.poll()
    path.unlink()
    reader.poll()  # unavailable
    _write(path, L3 + b"\n")
    poll = reader.poll()
    assert poll.rotation is True
    assert [line.data for line in poll.lines] == [L3]


def test_multibyte_utf8_offsets_are_byte_based(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    raw = '{"note": "caf\u00e9"}'.encode("utf-8") + b"\n"
    _write(path, raw + L1 + b"\n")
    reader = JsonlFileReader(path)
    poll = reader.poll()
    assert [line.data for line in poll.lines] == [raw[:-1], L1]
    assert poll.lines[1].start_offset == len(raw)
