# Env Hardcode Removal & Config Templates Specification

## Goal

Remove hardcoded secrets and IPv4/IPv6 connection values from `docker-compose.yml` and `lavalink/application.yml`, provide a complete `.env.example` template for those values, keep `settings Example.json` bot-token fields as-is (verified complete), add config-load tests, and require a post-implementation code review before considering the work done.

---

## Scope Decisions (Locked)

| Decision | Choice |
|---|---|
| Hardcode scope | **B** — YouTube tokens + IPv4/IPv6 wiring + compose secrets (`YT_CIPHER_API_TOKEN`, `CLOUDFLARED_TOKEN`) |
| Where IP lives | **A** — `.env` only (not `settings.json`) |
| IP preference model | **C** — Manual `IP_PREFERENCE` + concrete `YT_CIPHER_HOST` / `REMOTE_CIPHER_URL`; free-form `IP_BLOCKS` CIDR |
| Settings template | **A** — No new settings fields; verify existing bot token placeholders only |
| Approach | **1** — Env-only + compose/yml `${VAR}` substitution (no yml generator, no settings→env sync) |
| Auto-detect IPv6 | **No** — Operator sets preference and host/URL manually |

Out of scope:
- Dashboard settings/env templates
- Auto-detecting host IPv6 capability at startup
- Moving Lavalink server password (`youshallnotpass`) or Mongo image config into `.env` (unless already covered by existing bot env fallbacks)
- Changing Discord bot runtime networking / `Ping` AF_INET behavior

---

## Affected Paths

| Path | Change |
|---|---|
| `my_vocard_setup/.env.example` | **Create** — full template for secrets, tokens, IP |
| `my_vocard_setup/docker-compose.yml` | **Modify** — replace hardcoded `HOST`, `API_TOKEN`, Cloudflare tunnel token with env refs; wire ytcipher `env_file` if needed |
| `my_vocard_setup/lavalink/application.yml` | **Modify** — replace hardcoded remoteCipher URL/password and `ipBlocks` CIDRs with `${VAR}` |
| `my_vocard_setup/settings Example.json` | **Verify only** — ensure `token`, `client_id`, `genius_token`, `nodes.*.yt_ratelimit.tokens` remain present; no new keys |
| `my_vocard_setup/tests/test_config_templates.py` | **Create** — config/template load and hardcode-absence tests |
| `.superpower/plans/` | Later: implementation plan including final code-review task |

---

## 1. Environment Template

### 1.1 Required keys in `.env.example`

**Bot (also readable via `settings.json` / `Config`):**
- `TOKEN`
- `CLIENT_ID`
- `GENIUS_TOKEN`
- `MONGODB_URL`
- `MONGODB_NAME`

**YouTube / Lavalink plugin:**
- `YOUTUBE_OAUTH_REFRESH_TOKEN`
- `YOUTUBE_POT_TOKEN`
- `YOUTUBE_POT_VISITOR_DATA`

**Cipher + IP:**
- `IP_PREFERENCE` — one of `ipv4` | `ipv6` | `dual`
- `IP_BLOCKS` — single CIDR string (IPv4 or IPv6), operator-supplied
- `YT_CIPHER_HOST` — bind address for yt-cipher (`0.0.0.0` or `::`)
- `REMOTE_CIPHER_URL` — full URL Lavalink uses (e.g. `http://127.0.0.1:8001` or `http://[::1]:8001`)
- `YT_CIPHER_API_TOKEN` — shared secret for yt-cipher API and Lavalink `remoteCipher.password`

**Tunnel:**
- `CLOUDFLARED_TOKEN`

Template values must be placeholders only (empty or `YOUR_*`), never real secrets.

### 1.2 Manual IP preference mapping (documented in `.env.example` comments)

| `IP_PREFERENCE` | `YT_CIPHER_HOST` | `REMOTE_CIPHER_URL` |
|---|---|---|
| `ipv4` | `0.0.0.0` | `http://127.0.0.1:8001` |
| `ipv6` | `::` | `http://[::1]:8001` |
| `dual` | `::` | `http://[::1]:8001` |

Compose and Lavalink **do not** branch on `IP_PREFERENCE`. They consume the concrete host/URL vars. `IP_PREFERENCE` exists for operator intent + tests that validate the chosen triple is consistent with the table above.

`IP_BLOCKS` is independent: operator pastes the CIDR that matches their VPS (v4 or v6). No auto-selection from preference.

---

## 2. Compose & Lavalink Wiring

### 2.1 `docker-compose.yml`

- `ytcipher.environment.HOST` ← `${YT_CIPHER_HOST}` (or equivalent compose env form)
- `ytcipher.environment.API_TOKEN` ← `${YT_CIPHER_API_TOKEN}`
- Prefer `env_file: .env` on `ytcipher` (and `cloudflared` if needed) so substitution is reliable
- `cloudflared.command` uses `${CLOUDFLARED_TOKEN}` instead of an inline JWT
- Existing `lavalink` / `vocard` `env_file: .env` remain
- Remove any committed real secrets from this file

### 2.2 `lavalink/application.yml`

- `plugins.youtube.remoteCipher.url` ← `${REMOTE_CIPHER_URL:...}`
- `plugins.youtube.remoteCipher.password` ← `${YT_CIPHER_API_TOKEN:...}`
- Keep existing `${YOUTUBE_OAUTH_REFRESH_TOKEN:}`, `${YOUTUBE_POT_TOKEN:}`, `${YOUTUBE_POT_VISITOR_DATA:}`
- Both `ipBlocks` lists (under `plugins.youtube.ratelimit` and `lavalink.server.ratelimit`) use a single list entry `${IP_BLOCKS:...}` (one CIDR supported via env in this design)
- No remaining hardcoded former production CIDR `2600:1900:4080:5ba::/64` or former cipher password/token strings

### 2.3 Settings

- Do not add YouTube OAuth/POT, IP preference, or cipher keys to `settings Example.json`
- Confirm placeholders: `token`, `client_id`, `genius_token`, `nodes.DEFAULT.yt_ratelimit.tokens` (array)

---

## 3. Testing

Create `my_vocard_setup/tests/test_config_templates.py` covering:

1. **`.env.example` completeness** — required keys from §1.1 present; values are placeholders (no JWT-like Cloudflare token, no former hardcoded cipher token)
2. **IP preference mapping table** — for each of `ipv4` / `ipv6` / `dual`, expected host/URL pair matches §1.2 (pure unit table test; may live as a small shared constant used by docs comments and tests)
3. **`application.yml` substitutions** — file text contains env placeholders for remoteCipher URL/password, IP_BLOCKS, YouTube tokens; does not contain the old hardcoded CIDR or old cipher password
4. **`docker-compose.yml` substitutions** — no inline Cloudflare JWT; no inline former `API_TOKEN` value; references env for cipher host/token and cloudflared token
5. **Settings template load** — load `settings Example.json` as JSON; assert bot token-related keys exist and types are correct (`tokens` is a list)
6. **Config env fallback** — with a temp settings file omitting secrets and env vars set, `Config` (resetting singleton as other tests do if needed) reads `TOKEN` / `CLIENT_ID` / `GENIUS_TOKEN` from the environment

Tests must be runnable with `pytest` without Docker, Discord, or live Lavalink.

---

## 4. Post-Implementation Code Review

After implementation tasks and tests pass:

1. Dispatch a code-reviewer subagent per `requesting-code-review` skill against the full feature diff (`BASE_SHA` = commit before this work, `HEAD_SHA` = current HEAD)
2. Fix **Critical** and **Important** findings before marking complete
3. Record Minor items only if deferred explicitly

This review step is part of the delivery definition of done, not optional polish.

---

## 5. Security Notes

- `.env` remains gitignored; only `.env.example` is committed
- Rotating any secrets that were previously committed in `docker-compose.yml` / `application.yml` is **recommended for the operator** after this change (out of repo automation scope, but call out in plan/PR)
- Do not reintroduce real tokens into templates, compose, or tests

---

## Success Criteria

- No hardcoded cipher API token, Cloudflare tunnel token, remoteCipher password/URL, or production IPv6 CIDR remain in compose/yml
- `.env.example` documents all §1.1 keys and the manual IP mapping table
- `settings Example.json` still has complete bot-side token placeholders and no new IP/YouTube-plugin fields
- Config/template tests pass under pytest
- Code review completed with Critical/Important issues resolved
