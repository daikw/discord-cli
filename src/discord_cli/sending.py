"""Single-message sends without retries, with explicit delivery uncertainty."""

import math
import re

import httpx

from .config import API_BASE

# Discord Create Message limits; see the command documentation in README.
CONTENT_LIMIT = 2000
NONCE_LIMIT = 25


def snowflake(value):
    if (not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value)
            or int(value) >= 2**64):
        raise ValueError("Channel and message IDs must be positive uint64 decimal strings.")
    return value


def build_payload(content, nonce):
    if not isinstance(content, str) or not content.strip() or len(content) > CONTENT_LIMIT:
        raise ValueError("Content must contain text and be at most 2000 characters.")
    try:
        content.encode("utf-8")
    except UnicodeError:
        raise ValueError("Content must be valid Unicode text.") from None
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,25}", nonce):
        raise ValueError("Nonce must be 1-25 ASCII letters, digits, underscores or hyphens.")
    return {
        "content": content,
        "allowed_mentions": {"parse": [], "replied_user": False},
        "nonce": nonce,
        "enforce_nonce": True,
    }


def make_client(token):
    if not token or not all("!" <= char <= "~" for char in token):
        raise ValueError("DISCORD_TOKEN is missing or invalid.")
    return httpx.Client(
        base_url=API_BASE,
        headers={"Authorization": token},
        follow_redirects=False,
        trust_env=False,
    )


def json_object(response):
    try:
        value = response.json()
    except (ValueError, UnicodeError):
        return {}
    return value if isinstance(value, dict) else {}


def retry_after(response):
    value = json_object(response).get("retry_after")
    try:
        if type(value) in (int, float) and 0 <= value and math.isfinite(value):
            return value
    except OverflowError:
        pass
    return None


def send_once(client, channel, payload):
    result = {"channel_id": channel, "nonce": payload["nonce"]}
    path = f"/channels/{channel}/messages"
    unknown = {
        **result, "status": "outcome_unknown",
        "error": "Delivery is unknown. Inspect the channel before any retry; nothing was resent.",
    }
    try:
        response = client.post(path, json=payload)
    except (httpx.HTTPError, OSError, KeyboardInterrupt):
        return unknown

    if 400 <= response.status_code < 500:
        rejected = {
            **result, "status": "not_sent", "http_status": response.status_code,
            "error": "Discord rejected the request; nothing was resent.",
        }
        if response.status_code == 429:
            rejected["retry_after"] = retry_after(response)
        return rejected
    if not response.is_success:
        return {**unknown, "http_status": response.status_code}

    posted = json_object(response)
    try:
        message_id = snowflake(posted.get("id"))
    except ValueError:
        return unknown

    # Preserve the acknowledged ID even when the later read-back cannot be verified.
    unverified = {
        **result, "status": "sent_unverified", "message_id": message_id,
        "error": "Discord returned a message ID, but verification failed. Inspect it; do not resend.",
    }
    if posted.get("channel_id") != channel or posted.get("content") != payload["content"]:
        return unverified
    try:
        checked = client.get(f"{path}/{message_id}")
    except (httpx.HTTPError, OSError, KeyboardInterrupt):
        return unverified
    if not checked.is_success:
        return {**unverified, "verification_http_status": checked.status_code}
    data = json_object(checked)
    if (data.get("id") != message_id or data.get("channel_id") != channel
            or data.get("content") != payload["content"]):
        return unverified
    return {**result, "status": "sent_verified", "message_id": message_id}
