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


def test_chime_is_on_unless_muted(tmp_path):
    base = '[calendar]\nics_url = "https://example.com/cal.ics"\n'
    assert load_config(write(tmp_path, base)).chime is True
    assert load_config(write(tmp_path, base + "[sound]\nchime = false\n")).chime is False


GRAPH = '[calendar]\nsource = "graph"\n[graph]\nclient_id = "11111111-2222-3333-4444-555555555555"\ntenant_id = "contoso.onmicrosoft.com"\n'


def test_ics_is_the_default_source(tmp_path):
    assert load_config(write(tmp_path, '[calendar]\nics_url = "https://example.com/cal.ics"\n')).source == "ics"


def test_graph_source_reads_the_ids(tmp_path):
    config = load_config(write(tmp_path, GRAPH))
    assert config.source == "graph"
    assert config.client_id == "11111111-2222-3333-4444-555555555555"
    assert config.tenant_id == "contoso.onmicrosoft.com"


def test_graph_source_needs_no_ics_link(tmp_path):
    assert load_config(write(tmp_path, GRAPH)).ics_url == ""


def test_graph_source_without_ids_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="client_id"):
        load_config(write(tmp_path, '[calendar]\nsource = "graph"\n'))


def test_malformed_client_id_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="client_id"):
        load_config(write(tmp_path, GRAPH.replace("11111111-2222-3333-4444-555555555555", "abc")))


def test_unknown_source_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="source"):
        load_config(write(tmp_path, '[calendar]\nsource = "exchange"\n'))


def test_default_config_is_ics_with_empty_graph_ids(tmp_path):
    from outlook_reminder.config import DEFAULT_CONFIG

    with pytest.raises(ConfigError, match="ics_url"):
        load_config(write(tmp_path, DEFAULT_CONFIG))
    graph = DEFAULT_CONFIG.replace('source = "ics"', 'source = "graph"')
    with pytest.raises(ConfigError, match="client_id"):
        load_config(write(tmp_path, graph))
