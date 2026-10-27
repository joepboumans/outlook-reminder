from pathlib import Path

import pytest

from outlook_reminder.config import ConfigError, load_config


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_reads_the_ics_link(tmp_path):
    config = load_config(write(tmp_path, '[calendar]\nics_url = "https://example.com/cal.ics"\n'))
    assert config.ics_url == "https://example.com/cal.ics"


def test_missing_file_explains_where_the_config_goes(tmp_path):
    with pytest.raises(ConfigError, match="config.toml"):
        load_config(tmp_path / "config.toml")


def test_missing_ics_link_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="ics_url"):
        load_config(write(tmp_path, "[calendar]\n"))


def test_invalid_toml_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, "[calendar\n"))


def test_email_is_optional(tmp_path):
    base = '[calendar]\nics_url = "https://example.com/cal.ics"\n'
    assert load_config(write(tmp_path, base)).email is None
    assert load_config(write(tmp_path, base + 'email = "me@example.com"\n')).email == "me@example.com"
