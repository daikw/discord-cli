"""Explicit single-message posting using the existing Discord credential."""

import json
import sys
import uuid

import click
import httpx

from .. import config, sending
from ..exceptions import NotAuthenticatedError
from ._output import (
    default_structured_format,
    emit_structured,
    error_payload,
    structured_output_options,
    success_payload,
)


def _emit(result, *, as_json, as_yaml):
    if "error" in result:
        payload = error_payload(result["status"], result["error"], details=result)
    else:
        payload = success_payload(result)
    if not emit_structured(payload, as_json=as_json, as_yaml=as_yaml):
        # Escape user-provided text and terminal controls, including dry-run content.
        click.echo(json.dumps(payload, ensure_ascii=True, indent=2))


@click.command("send")
@click.argument("channel")
@click.argument("content", required=False)
@click.option("--stdin", "from_stdin", is_flag=True, help="Read text from stdin; preserve newlines.")
@click.option("--nonce", help="Reuse only for the same send intent; deduplication is temporary.")
@click.option("--dry-run", is_flag=True, help="Preview without requiring a token or sending HTTP.")
@click.option("--yes", is_flag=True, help="Send one message and fetch it to verify; never retry.")
@structured_output_options
def dc_send(channel, content, from_stdin, nonce, dry_run, yes, as_json, as_yaml):
    """Send text to CHANNEL (an exact channel or thread ID).

    Requires exactly one of --yes or --dry-run. Mentions never notify anyone.
    A failed verification can follow a successful send: inspect before retrying.
    """
    # Reject conflicting output flags before any external side effect.
    default_structured_format(as_json=as_json, as_yaml=as_yaml)
    try:
        if yes == dry_run:
            raise ValueError("Choose exactly one of --yes or --dry-run.")
        channel = sending.snowflake(channel)
        if from_stdin == (content is not None):
            raise ValueError("Provide either text or --stdin, but not both.")
        if from_stdin:
            content = sys.stdin.read(sending.CONTENT_LIMIT + 1)
        if nonce is None:
            nonce = uuid.uuid4().hex[:sending.NONCE_LIMIT]
        payload = sending.build_payload(content, nonce)
    except (ValueError, UnicodeError, OSError):
        _emit({
            "status": "not_sent",
            "error": "Invalid input: choose --yes or --dry-run; use an exact channel ID, "
                     "nonempty UTF-8 text (up to 2000 characters), and a valid nonce. "
                     "Provide text or --stdin, but not both.",
        }, as_json=as_json, as_yaml=as_yaml)
        raise SystemExit(2) from None

    if dry_run:
        _emit({"status": "dry_run", "channel_id": channel, "payload": payload},
              as_json=as_json, as_yaml=as_yaml)
        return

    try:
        token = config.get_token()
        if not token or not all("!" <= char <= "~" for char in token):
            raise ValueError("Invalid credential")
    except (NotAuthenticatedError, ValueError):
        _emit({"status": "not_sent", "error": "DISCORD_TOKEN is missing or invalid."},
              as_json=as_json, as_yaml=as_yaml)
        raise SystemExit(1) from None

    result = {
        "status": "not_sent", "channel_id": channel, "nonce": nonce,
        "error": "Could not initialize the HTTP client.",
    }
    try:
        with sending.make_client(token) as client:
            click.echo(f"Sending to channel {channel} (nonce {nonce}); no automatic retries.", err=True)
            result = sending.send_once(client, channel, payload)
    except (httpx.HTTPError, OSError, ValueError):
        # Keep an acknowledged result if closing the client fails after sending.
        pass
    _emit(result, as_json=as_json, as_yaml=as_yaml)
    if result["status"] != "sent_verified":
        raise SystemExit(1)
