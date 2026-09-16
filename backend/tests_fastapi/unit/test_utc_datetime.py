from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import mysql

from aidevops.types import UTCDateTime, ensure_utc


def test_mysql_bind_normalizes_to_naive_utc_and_reload_restores_timezone() -> None:
    type_ = UTCDateTime()
    local = datetime(2026, 9, 12, 8, 0, tzinfo=timezone(timedelta(hours=8)))
    stored = type_.process_bind_param(local, mysql.dialect())
    assert stored == datetime(2026, 9, 12, 0, 0)
    assert stored.tzinfo is None
    loaded = type_.process_result_value(stored, mysql.dialect())
    assert loaded.tzinfo == timezone.utc
    assert loaded.isoformat().endswith("+00:00")


def test_naive_driver_timestamp_is_assumed_to_be_stored_utc() -> None:
    assert ensure_utc(datetime(2026, 9, 12)).tzinfo == timezone.utc
