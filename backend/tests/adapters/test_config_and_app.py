from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.main import create_app

ENV = {"COZYTOUCH_USERNAME": "user@example.invalid", "COZYTOUCH_PASSWORD": "secret"}


def test_defaults():
    s = Settings.from_env(ENV)
    assert (s.poll_interval, s.db_path, s.backup_keep, s.retention_days_raw) == (300, Path("/data/pac.db"), 14, 0)


def test_off_peak_hours():
    assert Settings.from_env(ENV).off_peak_hours == ((98, 398), (848, 1028))
    assert Settings.from_env({**ENV, "OFF_PEAK_HOURS": ""}).off_peak_hours == ((98, 398), (848, 1028))
    assert Settings.from_env({**ENV, "OFF_PEAK_HOURS": " 22:00-06:00 "}).off_peak_hours == ((1320, 360),)
    assert Settings.from_env({**ENV, "OFF_PEAK_HOURS": "off"}).off_peak_hours == ()


def test_secrets_are_not_in_repr():
    assert "secret" not in repr(Settings.from_env(ENV)) and "user@" not in repr(Settings.from_env(ENV))


@pytest.mark.parametrize(
    "override",
    [
        {"COZYTOUCH_PASSWORD": ""},
        {"POLL_INTERVAL_SECONDS": "59"},
        {"POLL_INTERVAL_SECONDS": "abc"},
        {"BACKUP_KEEP": "0"},
        {"RETENTION_DAYS_RAW": "-1"},
        {"LOG_LEVEL": "LOUD"},
        {"OFF_PEAK_HOURS": "1h38-6h38"},
        {"OFF_PEAK_HOURS": "25:00-06:00"},
        {"OFF_PEAK_HOURS": "06:00-06:00"},
    ],
)
def test_invalid_config(override):
    with pytest.raises(ConfigError):
        Settings.from_env({**ENV, **override})


def test_lifespan_builds_and_closes_without_network(tmp_path):
    settings = Settings.from_env({**ENV, "DB_PATH": str(tmp_path / "pac.db"), "BACKUP_DIR": str(tmp_path / "b")})
    app = create_app(settings, start_scheduler=False)
    with TestClient(app) as client:
        container = client.app.state.container
        assert container.semantics.equipment
        assert client.get("/api/health").status_code == 200
    assert (tmp_path / "pac.db").exists()
    assert container.session.closed
