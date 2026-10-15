"""Pay catalog installs use native OAuth or a separate local CLI connection."""

from pathlib import Path

import pytest

from hermes_cli import mcp_catalog
from hermes_cli.config import load_config, save_config


@pytest.fixture(autouse=True)
def offline_install(monkeypatch):
    # Config writes use the temporary HERMES_HOME provided by tests/conftest.py.
    monkeypatch.setattr(mcp_catalog, "_probe_tools", lambda name: None)


def install(name):
    manifest = Path(__file__).resolve().parents[2] / "optional-mcps" / name / "manifest.yaml"
    mcp_catalog.install_entry(mcp_catalog._parse_manifest(manifest), enable=True)


def test_hosted_pay_replaces_legacy_stdio_without_local_cli():
    config = load_config()
    config["mcp_servers"] = {
        "pay": {"command": "pay", "args": ["mcp"], "env": {"PAY_FORCE_ELICITATION": "1"}},
    }
    save_config(config)

    install("pay")

    server = load_config()["mcp_servers"]["pay"]
    assert server["url"] == "https://connect.pay.sh/mcp"
    assert server["auth"] == "oauth"
    assert server["enabled"] is True
    assert not {"command", "args", "env", "headers"} & server.keys()


def test_local_and_hosted_pay_can_coexist():
    install("pay")
    hosted = load_config()["mcp_servers"]["pay"]
    install("pay-cli")

    servers = load_config()["mcp_servers"]
    assert servers["pay"] == hosted
    local = servers["pay-cli"]
    assert local["command"] == "pay"
    assert local["args"] == ["mcp"]
    assert local["env"]["PAY_FORCE_ELICITATION"] == "1"
    assert local["enabled"] is True
    assert "url" not in local
