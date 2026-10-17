# Changelog

## 0.2.8+daikw.1

- Add `discord dc send` with offline preview, explicit send intent, suppressed mentions, and read-back verification.
- Preserve message IDs and distinguish uncertain delivery from failed verification without automatic POST retries.
- Keep the original executable, credential environment variable, and local database paths.
- Pin dependencies to the versions already resolved by the upstream lockfile for the fork installation.

## 0.2.3

- Add public-release readiness improvements for documentation, packaging, and CI.
- Add safer channel resolution with ambiguity errors for local query and data commands.
- Add `timeline --json` and make `sync-all` discover channels directly from the Discord API.
- Clarify user-token risk and optional AI installation requirements in the docs.
