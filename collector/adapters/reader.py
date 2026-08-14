"""Incremental JSONL file reader with byte-accurate cursor accounting.

The bridge writes an append-only JSONL stream to a single file. The
reader:

* never loads the whole file - only the bytes after the persisted
  cursor offset are read on each poll
* leaves a trailing line without a newline *held* until it completes
  (a line is only published once a full line terminator is seen)
* detects rotation / replacement (new inode, or size shrank below the
  cursor) and signals :attr:`PollResult.rotation` so the pipeline can
  reset the cursor
* reports transient unavailability (missing file, read error) without
  advancing the cursor

Offsets are absolute byte offsets from the start of the file and always
align to line boundaries: ``byte_offset`` is the first byte of the next
line that has NOT yet been fully consumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawLine:
    """One complete line of raw input (without the trailing newline)."""

    data: bytes
    start_offset: int

    @property
    def end_offset(self) -> int:
        """Byte offset one past the line content (excludes the newline)."""
        return self.start_offset + len(self.data)

    def to_text(self) -> str:
        return self.data.decode("utf-8")


@dataclass(frozen=True)
class PollResult:
    """Snapshot of one poll cycle.

    ``lines`` - complete lines discovered since the previous poll
    ``offset`` - the new cursor position (start of next un-consumed line)
    ``held_partial`` - a partial line without a terminator is being held
    ``rotation`` - file replaced or shrunk below the cursor; restarting
        from offset 0 is required to re-read the new stream
    ``unavailable`` - file unreadable this poll; nothing advanced
    ``reads`` - total bytes buffered during this poll (for diagnostics)
    """

    lines: tuple[RawLine, ...] = ()
    offset: int = 0
    held_partial: bool = False
    rotation: bool = False
    unavailable: bool = False
    reads: int = 0


class JsonlFileReader:
    """Append-only JSONL reader keyed to a byte cursor."""

    def __init__(self, path: Path, *, start_offset: int = 0) -> None:
        self._path = path
        self._offset = max(start_offset, 0)
        self._partial: bytes = b""
        self._identity: tuple[int, int] | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def offset(self) -> int:
        """Current byte offset (start of the next un-consumed line)."""
        return self._offset

    @property
    def holds_partial(self) -> bool:
        return bool(self._partial)

    def reset(self) -> None:
        """Drop all state; the next poll restarts from byte zero."""
        self._offset = 0
        self._partial = b""
        self._identity = None

    def poll(self) -> PollResult:
        """Read complete lines appended since the previous poll."""
        try:
            stat = self._path.stat()
        except OSError:
            return PollResult(offset=self._offset, unavailable=True)

        identity = (stat.st_dev, stat.st_ino)
        rotation = False

        if self._identity is not None and identity != self._identity:
            # File was replaced (new inode): the tail is a new stream.
            # A held partial line from the old stream must be discarded;
            # the event it would have completed is simply re-read.
            self.reset()
            rotation = True
        elif stat.st_size < self._offset:
            # Shrunk below our cursor: replaced or corrupted; restart.
            self.reset()
            rotation = True

        self._identity = identity

        if rotation:
            # Wipe the partial buffer: it belongs to the previous stream.
            self._partial = b""

        if stat.st_size <= self._offset:
            return PollResult(
                offset=self._offset, held_partial=self.holds_partial, rotation=rotation
            )

        reads = 0
        try:
            with self._path.open("rb") as fh:
                fh.seek(self._offset + len(self._partial))
                chunk = fh.read()
            reads = len(chunk)
        except OSError:
            return PollResult(
                offset=self._offset,
                held_partial=self.holds_partial,
                rotation=rotation,
                unavailable=True,
            )

        if not chunk:
            return PollResult(
                offset=self._offset, held_partial=self.holds_partial, rotation=rotation, reads=reads
            )

        # Reassemble held partial + new chunk, then frame on newlines.
        # self._offset marks the START of the held partial line (the
        # crash-safe resume point); the read began len(_partial) bytes
        # later, so line start offsets are computed from _offset.
        buffer = self._partial + chunk
        lines: list[RawLine] = []
        cursor = self._offset

        if buffer.endswith(b"\n"):
            frames = buffer.split(b"\n")
            frames = frames[:-1]  # trailing empty element after the final newline
            new_partial = b""
            new_offset = self._offset + len(self._partial) + len(chunk)
        else:
            fragments = buffer.rsplit(b"\n", 1)
            if len(fragments) == 1:
                # No newline anywhere: everything stays partial.
                frames = []
                new_partial = buffer
                new_offset = self._offset
            else:
                frames = [fragments[0]]
                new_partial = fragments[1]
                new_offset = self._offset + len(self._partial) + len(chunk) - len(new_partial)

        for frame in frames:
            lines.append(RawLine(data=frame, start_offset=cursor))
            cursor += len(frame) + 1

        self._partial = new_partial
        self._offset = new_offset

        return PollResult(
            lines=tuple(lines),
            offset=self._offset,
            held_partial=self.holds_partial,
            rotation=rotation,
            reads=reads,
        )


__all__ = ["JsonlFileReader", "PollResult", "RawLine"]
