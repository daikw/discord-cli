from click.testing import CliRunner

from discord_cli.cli.main import cli


def test_send_is_unavailable_without_accessing_credentials(monkeypatch):
    from discord_cli import config

    def unexpected_token_access():
        raise AssertionError("Removed command must not request credentials")

    monkeypatch.setattr(config, "get_token", unexpected_token_access)
    result = CliRunner().invoke(cli, ["dc", "send", "123", "text", "--yes"])
    assert result.exit_code == 2
    assert "No such command 'send'" in result.output


def test_read_commands_remain_available():
    result = CliRunner().invoke(cli, ["dc", "--help"])
    assert result.exit_code == 0
    for command in ("history", "sync", "search", "channels", "guilds"):
        assert command in result.output
    assert "send" not in result.output
