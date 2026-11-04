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


def test_sign_in_is_only_for_the_graph_source(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text('[calendar]\nics_url = "https://example.com/cal.ics"\n')
    assert main(["--config", str(path), "--sign-in"]) == 2
    assert "graph" in capsys.readouterr().err


def test_graph_config_builds_the_graph_source(tmp_path):
    from outlook_reminder.cli import make_source
    from outlook_reminder.config import load_config
    from outlook_reminder.graph import GraphSource

    path = tmp_path / "config.toml"
    path.write_text('[calendar]\nsource = "graph"\n[graph]\n'
                    'client_id = "11111111-2222-3333-4444-555555555555"\ntenant_id = "t"\n')
    assert isinstance(make_source(load_config(path)), GraphSource)
