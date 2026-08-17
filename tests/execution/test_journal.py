"""Durable execution journal: append-only audit + idempotency projection."""

from __future__ import annotations

import sqlite3

import pytest

from execution.errors import DuplicateCommandError, JournalError
from execution.journal import ExecutionJournal
from execution.models import CommandState, ExecutionCommand, ExecutionResult
from tests.execution.factories import make_command


@pytest.fixture
def journal(tmp_path: object) -> ExecutionJournal:
    path = str(tmp_path) + "/journal.db"  # type: ignore[operator]
    j = ExecutionJournal(path)
    yield j
    j.close()


class TestCreate:
    def test_create_persists_created_state(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        stored = journal.get_command(command.command_id)
        assert stored is not None
        assert stored.state is CommandState.CREATED
        assert stored.trade_id == command.trade_id
        assert stored.payload["command_id"] == command.command_id

    def test_duplicate_command_id_rejected(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        with pytest.raises(DuplicateCommandError):
            journal.create_command(command)

    def test_active_trade_can_only_have_one_command(self, journal: ExecutionJournal) -> None:
        first = make_command()
        journal.create_command(first)
        second = ExecutionCommand(
            command_id=make_command().command_id,
            trade_id=first.trade_id,
            symbol=first.symbol,
            direction=first.direction,
            volume=first.volume,
            entry_type=first.entry_type,
            sl=first.sl,
            created_at=first.created_at,
            expires_at=first.expires_at,
        )
        with pytest.raises(DuplicateCommandError):
            journal.create_command(second)

    def test_terminal_trade_releases_trade_slot(self, journal: ExecutionJournal) -> None:
        first = make_command()
        journal.create_command(first)
        journal.record(first, "REJECTED", CommandState.REJECTED)
        second = ExecutionCommand(
            command_id=make_command().command_id,
            trade_id=first.trade_id,
            symbol=first.symbol,
            direction=first.direction,
            volume=first.volume,
            entry_type=first.entry_type,
            sl=first.sl,
            created_at=first.created_at,
            expires_at=first.expires_at,
        )
        journal.create_command(second)  # no exception


class TestAppendOnly:
    def test_update_is_forbidden(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        journal.record(command, "VALIDATE_OK", CommandState.VALIDATED)
        with pytest.raises(sqlite3.IntegrityError):
            with journal._conn:  # noqa: SLF001 - direct trigger check
                journal._conn.execute(  # noqa: SLF001
                    "UPDATE execution_journal SET payload_json = '{}' WHERE seq = 1"
                )

    def test_delete_is_forbidden(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        journal.record(command, "VALIDATE_OK", CommandState.VALIDATED)
        with pytest.raises(sqlite3.IntegrityError):
            with journal._conn:  # noqa: SLF001
                journal._conn.execute("DELETE FROM execution_journal")  # noqa: SLF001

    def test_projection_table_is_updateable(self, journal: ExecutionJournal) -> None:
        """Only the audit is immutable; state bookkeeping must move."""
        command = make_command()
        journal.create_command(command)
        journal.record(command, "VALIDATE_OK", CommandState.VALIDATED)
        assert journal.get_command(command.command_id).state is CommandState.VALIDATED


class TestAudit:
    def test_events_ordered_with_payloads(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        journal.record(command, "VALIDATE_OK", CommandState.VALIDATED, {"note": "ok"})
        journal.record(command, "SUBMIT", CommandState.SUBMITTED)
        events = journal.events(command.command_id)
        assert [event.event_type for event in events] == [
            "VALIDATE_OK",
            "SUBMIT",
        ]
        assert events[0].payload == {"note": "ok"}
        assert events[1].state is CommandState.SUBMITTED
        assert events[0].seq < events[1].seq

    def test_result_stored_and_retrieved(self, journal: ExecutionJournal) -> None:
        command = make_command()
        journal.create_command(command)
        journal.record(command, "FULL_FILL", CommandState.FILLED)
        result = ExecutionResult.filled(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=command.created_at,
            broker_request_id="ORD-000001",
            filled_volume=command.volume,
            fill_price=4400.0,
            sl_applied=True,
        )
        journal.store_result(command, result)
        assert journal.get_result(command.command_id) == result
        assert journal.get_command(command.command_id).result == result

    def test_active_commands_exclude_terminal(self, journal: ExecutionJournal) -> None:
        live = make_command()
        done = make_command()
        journal.create_command(live)
        journal.create_command(done)
        journal.record(done, "REJECTED", CommandState.REJECTED)
        ids = {item.command_id for item in journal.active_commands()}
        assert live.command_id in ids
        assert done.command_id not in ids

    def test_journal_error_wraps_broken_writes(self, journal: ExecutionJournal) -> None:
        """A database failure inside record() surfaces as JournalError."""
        command = make_command()
        journal.create_command(command)
        with journal._conn:  # noqa: SLF001 - simulate a broken audit table
            journal._conn.execute("DROP TABLE execution_journal")  # noqa: SLF001
        with pytest.raises(JournalError):
            journal.record(command, "VALIDATE_OK", CommandState.VALIDATED)


class TestPersistence:
    def test_state_and_result_survive_reopen(self, tmp_path: object) -> None:
        db_path = str(tmp_path) + "/persist.db"  # type: ignore[operator]
        command = make_command()
        journal_a = ExecutionJournal(db_path)
        journal_a.create_command(command)
        journal_a.record(command, "SUBMIT", CommandState.SUBMITTED)
        result = ExecutionResult.failed(
            command_id=command.command_id,
            trade_id=command.trade_id,
            timestamp=command.created_at,
            error_code="X",
            error_message="boom",
        )
        journal_a.store_result(command, result)
        event_count = journal_a.event_count()
        journal_a.close()

        journal_b = ExecutionJournal(db_path)
        try:
            stored = journal_b.get_command(command.command_id)
            assert stored is not None
            assert stored.state is CommandState.SUBMITTED
            assert stored.result == result
            assert journal_b.event_count() == event_count
            assert len(journal_b.events(command.command_id)) == 1  # the SUBMIT line only
        finally:
            journal_b.close()
