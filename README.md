# discord-cli (daikw fork)

[![CI](https://github.com/daikw/discord-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/daikw/discord-cli/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/kabi_discord_cli.svg)](https://pypi.org/project/kabi-discord-cli/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)

> Fork of [jackwener/discord-cli](https://github.com/jackwener/discord-cli), adding single-message posting while preserving upstream read, search, and sync commands. The distribution name remains `kabi-discord-cli`; this fork is installed from a locally built wheel, not published to PyPI.

[中文](./README_CN.md)

## More Projects

- [xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli) — Xiaohongshu (小红书) CLI for notes and account workflows
- [twitter-cli](https://github.com/jackwener/twitter-cli) — Twitter/X CLI for timelines, bookmarks, and posting
- [bilibili-cli](https://github.com/jackwener/bilibili-cli) — Bilibili CLI for videos, users, search, and feeds
- [tg-cli](https://github.com/jackwener/tg-cli) — Telegram CLI for local-first sync, search, and export

Telethon-style local-first tooling for Discord: sync messages into SQLite, search them from the terminal, export structured results, and feed them to AI agents.

discord-cli uses the Discord HTTP API with a **user token** from your local session. It is meant for accounts you control, on machines you control.

## Warning

- discord-cli reads a Discord **user token** from your local Discord/browser session.
- Discord may restrict or suspend accounts that automate user-token traffic.
- Use it only on your own account and only if you understand the risk.

## Features

- Local-first SQLite storage for history, sync, search, export, and analytics
- `discord dc sync-all` discovers accessible text channels and bootstraps from the API
- Query commands support `--yaml` and `--json` for scripting and AI agent integration
- Non-TTY stdout defaults to YAML; override with `OUTPUT=yaml|json|rich|auto`
- Structured output contract: [SCHEMA.md](./SCHEMA.md)

> **AI Agent Tip:** Prefer `--yaml` for structured output unless a strict JSON parser is required. Use `-n` to limit results.
- Safer local channel resolution for `search`, `recent`, `today`, `export`, and `purge`

## Installation

Build the reviewed checkout and install its wheel as `discord`:

```bash
git clone https://github.com/daikw/discord-cli.git
cd discord-cli
uv sync --locked --extra dev
uv run --no-sync ruff check .
uv run --no-sync python -m pytest -q
uv build
uv export --locked --no-dev --no-emit-project --no-hashes \
  --format requirements-txt --output-file dist/runtime-constraints.txt
uv tool install --force --no-build --constraint dist/runtime-constraints.txt \
  ./dist/kabi_discord_cli-0.2.8+daikw.1-py3-none-any.whl
```

The executable name, `DISCORD_TOKEN`, and upstream database paths are unchanged.
Existing wrappers that inject `DISCORD_TOKEN` and invoke `~/.local/bin/discord`
continue to work; credentials should remain outside this repository.
Installing the upstream PyPI package instead will not include this fork's posting command.

## Posting one message

```bash
# Offline preview; no token or HTTP request is needed.
discord dc send CHANNEL_ID 'Message text' --dry-run --json

# Send once using the configured user token, then fetch the returned message ID.
discord dc send CHANNEL_ID 'Message text' --yes --json

# Read multiline text from stdin without trimming its final newline.
discord dc send CHANNEL_ID --stdin --yes --json < message.txt
```

Use an exact channel ID or an existing thread ID. Forum parent channels, new
threads, attachments, replies, edits, and deletes are not supported by `send`.
One of `--yes` or `--dry-run` is required. Content must contain non-whitespace
text and fit Discord's 2000-character limit. Mentions are disabled with
`allowed_mentions`; content is never split into multiple messages.

The command never automatically retries a POST, including on HTTP 429.
A valid `retry_after` is reported for 429 responses; wait that long before any
new attempt. Each send includes a nonce with `enforce_nonce: true`.
`--nonce VALUE` can reuse a preview's nonce or the same send intent, but should
never be reused for a different message. Discord only documents deduplication
for the same author over the past few minutes; it is not a permanent guarantee.
Running the command again without `--nonce` creates a new nonce and may duplicate
a previous message.

`sent_verified` means a read-back matched the message ID, channel, and exact
content. `sent_unverified` preserves the acknowledged ID when verification
fails. `outcome_unknown` means delivery could not be determined. A nonzero exit
status does **not** necessarily mean nothing was sent: inspect the channel and
message ID before retrying. Discord may normalize content, which also causes
exact verification to fail. Sending does not modify the local SQLite mirror;
use the existing sync commands when needed.

This remains user-token automation, not the official Bot authentication flow.
The warning above applies to both reading and posting. Dry-run only validates
the local request; it does not check account status or channel permissions.
Upstream's startup `.env` loading still applies, and an external credential
wrapper may decrypt its files before the CLI starts, even for dry-run.

## Quick Start

```bash
# Extract and save a token from your local Discord/browser session
discord auth --save

# Verify auth
discord status
discord whoami

# Explore guilds and channels
discord dc guilds
discord dc channels <guild_id>

# Bootstrap local storage
discord dc sync-all -n 500

# Query local cache
discord today
discord recent -n 50
discord search "rust" -c general --json
discord timeline --by hour --json
```

## Commands

### Auth & Account

| Command | Description |
|---------|-------------|
| `auth [--save]` | Extract a token from local Discord/browser session |
| `status` | Check if the configured token is valid |
| `whoami [--json]` | Show the current Discord profile |

### Discord API (`discord dc ...`)

| Command | Description |
|---------|-------------|
| `dc send CHANNEL [CONTENT] (--yes\|--dry-run) [--stdin] [--nonce VALUE] [--json]` | Post one text message with read-back verification |
| `dc guilds [--json]` | List joined guilds |
| `dc channels GUILD [--json]` | List text channels in a guild |
| `dc history CHANNEL [-n 1000]` | Fetch message history for one channel |
| `dc sync CHANNEL [-n 5000]` | Incrementally sync one channel |
| `dc sync-all [-n 5000]` | Discover and sync accessible text channels |
| `dc tail CHANNEL [--once]` | Poll and follow new messages like `tail -f` |
| `dc search GUILD KEYWORD [-c CHANNEL_ID] [--json]` | Use Discord native search |
| `dc members GUILD [--max 50] [--json]` | List guild members |
| `dc info GUILD [--json]` | Show guild info |

### Local Query

| Command | Description |
|---------|-------------|
| `search KEYWORD [-c CHANNEL] [-n 50] [--json]` | Search locally stored messages |
| `recent [-c CHANNEL] [--hours N] [-n 50] [--json]` | Show newest locally stored messages |
| `stats [--json]` | Message statistics per channel |
| `today [-c CHANNEL] [--json]` | Show today's messages |
| `top [-c CHANNEL] [--hours N] [--json]` | Top senders |
| `timeline [-c CHANNEL] [--hours N] [--by day\|hour] [--json]` | Activity timeline |

### Data

| Command | Description |
|---------|-------------|
| `export CHANNEL [-f text\|json] [-o FILE] [--hours N]` | Export stored messages |
| `purge CHANNEL [-y]` | Delete stored messages for a channel |

## Behavior Notes

- Most top-level query commands read from local SQLite, not directly from Discord.
- `discord dc sync-all` now bootstraps by discovering guilds and channels through the API, so it works on a fresh database.
- Channel names are resolved against the local database. If a name matches multiple channels, the CLI will stop and ask you to use a more specific name or a channel ID.

discord-cli also ships with [SKILL.md](./SKILL.md) for agent integration.

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run python -m pytest
uv build
```

## License

Apache-2.0
