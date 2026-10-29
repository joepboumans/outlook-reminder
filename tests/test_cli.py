from outlook_reminder.cli import main
from outlook_reminder.config import DEFAULT_CONFIG


def test_init_config_writes_the_default_config_when_none_exists(tmp_path):
    path = tmp_path / "outlook-reminder" / "config.toml"
    assert main(["--config", str(path), "--init-config"]) == 0
    assert path.read_text() == DEFAULT_CONFIG


def test_init_config_never_overwrites_an_existing_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("mine")
    assert main(["--config", str(path), "--init-config"]) == 0
    assert path.read_text() == "mine"


def test_missing_ics_link_exits_with_a_message(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text(DEFAULT_CONFIG)
    assert main(["--config", str(path)]) == 2
    assert "ics_url" in capsys.readouterr().err
