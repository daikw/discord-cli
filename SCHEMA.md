# Structured Output Schema

`discord-cli` uses a shared agent-friendly envelope for machine-readable output.

## Success

```yaml
ok: true
schema_version: "1"
data: ...
```

## Error

```yaml
ok: false
schema_version: "1"
error:
  code: channel_resolution_error
  message: Channel 'gen' matches multiple local channels.
```

## Notes

- `--yaml` and `--json` both use this envelope
- non-TTY stdout defaults to YAML
- query commands return arrays or dicts under `data`
- `status` returns `data.authenticated` plus `data.user`
- `whoami` returns `data.user`

## Single-message posting

`dc send` returns `data.status: dry_run` with `channel_id` and `payload`, or
`data.status: sent_verified` with `channel_id`, `nonce`, and `message_id`.

Failed outcomes use `error.code` and `error.details.status`:

- `not_sent`: rejected before sending or by a Discord 4xx response.
- `outcome_unknown`: delivery could not be determined; do not blindly resend.
- `sent_unverified`: Discord returned a message ID but the read-back did not
  verify; `error.details.message_id` is retained for inspection.

An HTTP failure may include `http_status` or `verification_http_status`.
For a POST 429, `retry_after` is a finite nonnegative number of seconds, or
`null` if the response did not provide a valid value. The command never retries
a POST automatically. Nonzero exit status does not imply that no message was sent.
