"""Offline checks for single-message delivery and its CLI boundary."""

import json
from unittest.mock import Mock

import httpx
import pytest
import yaml
from click.testing import CliRunner

from discord_cli.cli.main import cli

CHANNEL = "1301124969853358104"
MESSAGE = "1301124969853358105"
TOKEN = "synthetic-test-token"
CONTENT = "テスト本文 @everyone <@123>\nsecond line"


def message(**overrides):
    return {"id": MESSAGE, "channel_id": CHANNEL, "content": CONTENT, **overrides}


@pytest.fixture
def invoke(monkeypatch):
    from discord_cli import sending

    requests = []
    factory = Mock()
    monkeypatch.setenv("DISCORD_TOKEN", TOKEN)

    def run(args, handler=None, stdin="", token=TOKEN):
        requests.clear()
        factory.reset_mock()
        monkeypatch.setenv("DISCORD_TOKEN", token)

        def handle(request):
            requests.append(request)
            assert handler is not None, "Unexpected HTTP request"
            return handler(request)

        factory.side_effect = lambda credential: httpx.Client(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": credential},
            transport=httpx.MockTransport(handle),
            follow_redirects=False,
            trust_env=False,
        )
        monkeypatch.setattr(sending, "make_client", factory)
        result = CliRunner().invoke(cli, ["dc", "send", *args], input=stdin)
        return result, list(requests), factory

    return run


def data(result):
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "1"
    return payload["data"] if payload["ok"] else payload["error"]["details"]


def test_send_command_is_registered():
    result = CliRunner().invoke(cli, ["dc", "send", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output


def test_send_then_verify_exact_message(invoke):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--nonce", "test-intent", "--json"],
        lambda request: httpx.Response(200, json=message()),
    )
    assert result.exit_code == 0, result.output
    assert data(result) == {
        "status": "sent_verified", "channel_id": CHANNEL,
        "message_id": MESSAGE, "nonce": "test-intent",
    }
    assert [r.method for r in requests] == ["POST", "GET"]
    assert str(requests[0].url) == f"https://discord.com/api/v10/channels/{CHANNEL}/messages"
    assert str(requests[1].url) == f"https://discord.com/api/v10/channels/{CHANNEL}/messages/{MESSAGE}"
    assert requests[0].headers["Authorization"] == TOKEN
    assert json.loads(requests[0].content) == {
        "content": CONTENT, "nonce": "test-intent", "enforce_nonce": True,
        "allowed_mentions": {"parse": [], "replied_user": False},
    }
    assert TOKEN not in result.output


def test_dry_run_never_requests_token_or_opens_client(invoke, monkeypatch):
    from discord_cli import config

    monkeypatch.setattr(config, "get_token", Mock(side_effect=AssertionError("No auth")))
    result, requests, factory = invoke([CHANNEL, CONTENT, "--dry-run", "--json"], token="")
    assert result.exit_code == 0
    assert data(result)["status"] == "dry_run"
    assert data(result)["payload"]["content"] == CONTENT
    assert requests == []
    factory.assert_not_called()


def test_stdin_and_yaml(invoke):
    result, _, _ = invoke([CHANNEL, "--stdin", "--dry-run", "--yaml"], stdin=CONTENT)
    assert result.exit_code == 0
    assert yaml.safe_load(result.stdout)["data"]["payload"]["content"] == CONTENT


@pytest.mark.parametrize("args", [
    ["../users/@me", CONTENT, "--yes"], ["０１２３", CONTENT, "--yes"],
    ["0", CONTENT, "--yes"], [str(2**64), CONTENT, "--yes"],
    [CHANNEL, "", "--yes"], [CHANNEL, " \n\t", "--yes"],
    [CHANNEL, "x" * 2001, "--yes"], [CHANNEL, "\ud800", "--yes"],
    [CHANNEL, CONTENT], [CHANNEL, CONTENT, "--yes", "--dry-run"],
    [CHANNEL, "--yes"], [CHANNEL, CONTENT, "--stdin", "--yes"],
    [CHANNEL, CONTENT, "--yes", "--nonce", "x" * 26],
    [CHANNEL, CONTENT, "--yes", "--nonce", "bad\nnonce"],
    [CHANNEL, CONTENT, "--yes", "--json", "--yaml"],
])
def test_invalid_input_never_opens_client(invoke, args):
    result, requests, factory = invoke(args)
    assert result.exit_code == 2, result.output
    assert requests == []
    factory.assert_not_called()


def test_content_limit_boundary(invoke):
    result, _, _ = invoke([CHANNEL, "あ" * 2000, "--dry-run", "--json"])
    assert result.exit_code == 0
    assert len(data(result)["payload"]["content"]) == 2000


@pytest.mark.parametrize("token", ["", "bad\nsecret", "Bot secret", "あ"])
def test_missing_or_invalid_token_is_safe(invoke, token):
    result, requests, factory = invoke([CHANNEL, CONTENT, "--yes", "--json"], token=token)
    assert result.exit_code == 1
    assert data(result)["status"] == "not_sent"
    assert "secret" not in result.output
    assert requests == []
    factory.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_http_rejections_are_not_retried_or_echoed(invoke, status):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--json"],
        lambda request: httpx.Response(status, json={"message": TOKEN, "retry_after": 2.5}),
    )
    assert result.exit_code == 1
    assert data(result)["status"] == "not_sent"
    assert data(result)["http_status"] == status
    assert len(requests) == 1
    assert TOKEN not in result.output
    if status == 429:
        assert data(result)["retry_after"] == 2.5


@pytest.mark.parametrize("value", [10**400, float("inf"), float("nan"), -1, True, "secret", None])
def test_malformed_retry_delay_is_sanitized(invoke, value):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--json"],
        lambda request: httpx.Response(429, text=json.dumps({"retry_after": value})),
    )
    assert result.exit_code == 1
    assert data(result)["status"] == "not_sent"
    assert data(result)["retry_after"] is None
    assert len(requests) == 1


@pytest.mark.parametrize("response", [
    httpx.Response(500, text=TOKEN), httpx.Response(200, text="invalid json"),
    httpx.Response(200, json=[]), httpx.Response(200, json=message(id="../users/@me")),
    httpx.Response(307, headers={"Location": "https://example.invalid/steal"}),
])
def test_unknown_outcomes_and_redirects_never_retry(invoke, response):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--json"], lambda request: response,
    )
    assert result.exit_code == 1
    assert data(result)["status"] == "outcome_unknown"
    assert len(requests) == 1
    assert TOKEN not in result.output


@pytest.mark.parametrize("failed_method", ["POST", "GET"])
@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, OSError, KeyboardInterrupt])
def test_network_failure_preserves_delivery_uncertainty(invoke, failed_method, error_type):
    def handler(request):
        if request.method == failed_method:
            raise error_type(TOKEN)
        return httpx.Response(200, json=message())

    result, requests, _ = invoke([CHANNEL, CONTENT, "--yes", "--json"], handler)
    assert result.exit_code == 1
    assert data(result)["status"] == (
        "outcome_unknown" if failed_method == "POST" else "sent_unverified"
    )
    assert len(requests) == (1 if failed_method == "POST" else 2)
    if failed_method == "GET":
        assert data(result)["message_id"] == MESSAGE
    assert TOKEN not in result.output


@pytest.mark.parametrize("response", [
    httpx.Response(403), httpx.Response(200, text="bad json"),
    httpx.Response(200, json=message(content="different")),
    httpx.Response(200, json=message(channel_id="123")),
    httpx.Response(200, json=message(id="123")),
])
def test_acknowledged_send_preserves_id_when_readback_fails(invoke, response):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--json"],
        lambda request: httpx.Response(200, json=message()) if request.method == "POST" else response,
    )
    assert result.exit_code == 1
    assert data(result)["status"] == "sent_unverified"
    assert data(result)["message_id"] == MESSAGE
    assert [r.method for r in requests] == ["POST", "GET"]


def test_acknowledged_but_mismatched_post_does_not_verify_wrong_message(invoke):
    result, requests, _ = invoke(
        [CHANNEL, CONTENT, "--yes", "--json"],
        lambda request: httpx.Response(200, json=message(channel_id="123")),
    )
    assert result.exit_code == 1
    assert data(result)["status"] == "sent_unverified"
    assert data(result)["message_id"] == MESSAGE
    assert len(requests) == 1


def test_reusing_nonce_preserves_deduplication_payload(invoke):
    bodies = []
    for _ in range(2):
        result, requests, _ = invoke(
            [CHANNEL, CONTENT, "--yes", "--nonce", "same-intent", "--json"],
            lambda request: httpx.Response(200, json=message()),
        )
        assert result.exit_code == 0
        bodies.append(json.loads(requests[0].content))
    assert bodies[0] == bodies[1]
    assert bodies[0]["enforce_nonce"] is True


def test_client_disables_environment_proxy_and_redirects(monkeypatch):
    from discord_cli import sending

    constructor = Mock()
    monkeypatch.setattr(sending.httpx, "Client", constructor)
    sending.make_client(TOKEN)
    assert constructor.call_args.kwargs["trust_env"] is False
    assert constructor.call_args.kwargs["follow_redirects"] is False
    assert constructor.call_args.kwargs["base_url"] == "https://discord.com/api/v10"
