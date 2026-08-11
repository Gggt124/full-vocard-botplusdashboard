# Env Hardcode Removal & Config Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove hardcoded cipher/Cloudflare secrets and IPv4/IPv6 connection values from compose/Lavalink config, ship a complete `.env.example`, keep bot `settings Example.json` token fields as-is, add config-load tests, and finish with a code-review pass.

**Architecture:** Operators configure secrets and IP via `.env`. Compose and `application.yml` consume `${VAR}` only. `IP_PREFERENCE` is documentary + test-validated; runtime uses concrete `YT_CIPHER_HOST` / `REMOTE_CIPHER_URL` / `IP_BLOCKS`. A tiny Python mapping module holds the preference→defaults table for tests (not used by Docker at runtime).

**Tech Stack:** Docker Compose env interpolation, Lavalink/Spring `${VAR}` placeholders, Python 3 + pytest, existing `voicelink.config.Config` singleton.

## Global Constraints

- Scope **B** from spec: YouTube tokens + IP wiring + compose secrets (`YT_CIPHER_API_TOKEN`, `CLOUDFLARED_TOKEN`).
- IP lives in **`.env` only** — do not add IP/YouTube-plugin keys to `settings Example.json`.
- **No IPv6 auto-detect** — operator sets preference and host/URL manually.
- Compose/yml **must not branch** on `IP_PREFERENCE`; only consume concrete vars.
- `.env` stays gitignored; commit **only** `.env.example`.
- Never commit real secrets; templates use empty/`YOUR_*` placeholders.
- Forbidden residual strings (must not appear in compose/yml after changes):
  - `eouc2pn8-IcnqIYxQRimPaLQSWrMs-Yn`
  - `2600:1900:4080:5ba::/64`
  - Cloudflare JWT prefix `eyJhIjoiMTkwYTQ3OTczMjVjNTJkNzY1ZDFkOTRmYjcxM2U1MjQi`
- Definition of done includes **post-implementation code review** with Critical/Important fixes.
- Spec path: `.superpower/specs/2026-08-11-env-hardcode-templates-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `my_vocard_setup/ip_preference.py` | `IP_PREFERENCE_DEFAULTS` mapping table (`ipv4`/`ipv6`/`dual` → host + remote URL) |
| `my_vocard_setup/.env.example` | Template for all required env keys + commented mapping guidance |
| `my_vocard_setup/docker-compose.yml` | Wire cipher/cloudflared from env; remove hardcodes |
| `my_vocard_setup/lavalink/application.yml` | Wire remoteCipher, `IP_BLOCKS`, keep YouTube token placeholders |
| `my_vocard_setup/settings Example.json` | Verify only (no new keys) |
| `my_vocard_setup/tests/test_config_templates.py` | Template completeness, hardcode absence, settings load, Config env fallback, preference mapping |

---

### Task 1: IP preference mapping module + tests

**Files:**
- Create: `my_vocard_setup/ip_preference.py`
- Create: `my_vocard_setup/tests/test_config_templates.py`
- Test: `my_vocard_setup/tests/test_config_templates.py`

**Interfaces:**
- Consumes: nothing
- Produces: `IP_PREFERENCE_DEFAULTS: dict[str, dict[str, str]]` with keys `ipv4`, `ipv6`, `dual`; each value has `YT_CIPHER_HOST` and `REMOTE_CIPHER_URL`

- [ ] **Step 1: Write the failing tests for the mapping table**

```python
# my_vocard_setup/tests/test_config_templates.py
from ip_preference import IP_PREFERENCE_DEFAULTS


def test_ip_preference_defaults_cover_all_modes():
    assert set(IP_PREFERENCE_DEFAULTS) == {"ipv4", "ipv6", "dual"}


def test_ip_preference_ipv4_defaults():
    assert IP_PREFERENCE_DEFAULTS["ipv4"] == {
        "YT_CIPHER_HOST": "0.0.0.0",
        "REMOTE_CIPHER_URL": "http://127.0.0.1:8001",
    }


def test_ip_preference_ipv6_and_dual_defaults():
    expected = {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    }
    assert IP_PREFERENCE_DEFAULTS["ipv6"] == expected
    assert IP_PREFERENCE_DEFAULTS["dual"] == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_ip_preference_defaults_cover_all_modes my_vocard_setup/tests/test_config_templates.py::test_ip_preference_ipv4_defaults my_vocard_setup/tests/test_config_templates.py::test_ip_preference_ipv6_and_dual_defaults -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'ip_preference'` (or import error)

- [ ] **Step 3: Implement the mapping module**

```python
# my_vocard_setup/ip_preference.py
"""Manual IP preference → recommended cipher bind/URL defaults.

Compose and Lavalink do not read IP_PREFERENCE at runtime; operators copy
these defaults into YT_CIPHER_HOST / REMOTE_CIPHER_URL in `.env`.
"""

from __future__ import annotations

IP_PREFERENCE_DEFAULTS: dict[str, dict[str, str]] = {
    "ipv4": {
        "YT_CIPHER_HOST": "0.0.0.0",
        "REMOTE_CIPHER_URL": "http://127.0.0.1:8001",
    },
    "ipv6": {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    },
    "dual": {
        "YT_CIPHER_HOST": "::",
        "REMOTE_CIPHER_URL": "http://[::1]:8001",
    },
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_ip_preference_defaults_cover_all_modes my_vocard_setup/tests/test_config_templates.py::test_ip_preference_ipv4_defaults my_vocard_setup/tests/test_config_templates.py::test_ip_preference_ipv6_and_dual_defaults -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/ip_preference.py my_vocard_setup/tests/test_config_templates.py
git commit -m "feat(config): add IP preference defaults mapping and tests"
```

---

### Task 2: `.env.example` template + completeness tests

**Files:**
- Create: `my_vocard_setup/.env.example`
- Modify: `my_vocard_setup/tests/test_config_templates.py`
- Test: `my_vocard_setup/tests/test_config_templates.py`

**Interfaces:**
- Consumes: `IP_PREFERENCE_DEFAULTS` (for comment guidance only in `.env.example`)
- Produces: committed `.env.example` with required keys listed below

Required keys (exact names):
`TOKEN`, `CLIENT_ID`, `GENIUS_TOKEN`, `MONGODB_URL`, `MONGODB_NAME`, `YOUTUBE_OAUTH_REFRESH_TOKEN`, `YOUTUBE_POT_TOKEN`, `YOUTUBE_POT_VISITOR_DATA`, `IP_PREFERENCE`, `IP_BLOCKS`, `YT_CIPHER_HOST`, `REMOTE_CIPHER_URL`, `YT_CIPHER_API_TOKEN`, `CLOUDFLARED_TOKEN`

- [ ] **Step 1: Write failing tests for `.env.example`**

Append to `my_vocard_setup/tests/test_config_templates.py`:

```python
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = SETUP_DIR / ".env.example"

REQUIRED_ENV_KEYS = [
    "TOKEN",
    "CLIENT_ID",
    "GENIUS_TOKEN",
    "MONGODB_URL",
    "MONGODB_NAME",
    "YOUTUBE_OAUTH_REFRESH_TOKEN",
    "YOUTUBE_POT_TOKEN",
    "YOUTUBE_POT_VISITOR_DATA",
    "IP_PREFERENCE",
    "IP_BLOCKS",
    "YT_CIPHER_HOST",
    "REMOTE_CIPHER_URL",
    "YT_CIPHER_API_TOKEN",
    "CLOUDFLARED_TOKEN",
]

FORBIDDEN_SECRET_FRAGMENTS = [
    "eouc2pn8-IcnqIYxQRimPaLQSWrMs-Yn",
    "2600:1900:4080:5ba::/64",
    "eyJhIjoiMTkwYTQ3OTczMjVjNTJkNzY1ZDFkOTRmYjcxM2U1MjQi",
]


def _parse_env_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_exists_and_has_required_keys():
    assert ENV_EXAMPLE.is_file()
    keys = _parse_env_keys(ENV_EXAMPLE.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_ENV_KEYS if k not in keys]
    assert missing == []


def test_env_example_has_no_forbidden_secrets():
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_env_example_exists_and_has_required_keys my_vocard_setup/tests/test_config_templates.py::test_env_example_has_no_forbidden_secrets -v`

Expected: FAIL (`assert ENV_EXAMPLE.is_file()` false) or missing keys

- [ ] **Step 3: Create `.env.example`**

Create `my_vocard_setup/.env.example` with placeholder values and comments documenting the IP mapping table from Task 1 (ipv4 → `0.0.0.0` / `http://127.0.0.1:8001`; ipv6/dual → `::` / `http://[::1]:8001`). Example shape:

```env
# Bot (settings.json can override; these are fallbacks)
TOKEN=YOUR_BOT_TOKEN
CLIENT_ID=YOUR_BOT_CLIENT_ID
GENIUS_TOKEN=YOUR_GENIUS_TOKEN
MONGODB_URL=mongodb://mongo:27017
MONGODB_NAME=vocard

# Lavalink YouTube plugin
YOUTUBE_OAUTH_REFRESH_TOKEN=
YOUTUBE_POT_TOKEN=
YOUTUBE_POT_VISITOR_DATA=

# IP: set IP_PREFERENCE for intent, then copy matching defaults into HOST/URL.
# ipv4 -> YT_CIPHER_HOST=0.0.0.0  REMOTE_CIPHER_URL=http://127.0.0.1:8001
# ipv6/dual -> YT_CIPHER_HOST=::  REMOTE_CIPHER_URL=http://[::1]:8001
IP_PREFERENCE=ipv6
IP_BLOCKS=YOUR_CIDR_BLOCK
YT_CIPHER_HOST=::
REMOTE_CIPHER_URL=http://[::1]:8001
YT_CIPHER_API_TOKEN=YOUR_YT_CIPHER_API_TOKEN

# Cloudflare tunnel
CLOUDFLARED_TOKEN=YOUR_CLOUDFLARED_TOKEN
```

Do not paste any former production secrets.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_env_example_exists_and_has_required_keys my_vocard_setup/tests/test_config_templates.py::test_env_example_has_no_forbidden_secrets -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/.env.example my_vocard_setup/tests/test_config_templates.py
git commit -m "docs(env): add .env.example with bot, YouTube, IP, and tunnel keys"
```

---

### Task 3: De-hardcode `docker-compose.yml` + absence tests

**Files:**
- Modify: `my_vocard_setup/docker-compose.yml`
- Modify: `my_vocard_setup/tests/test_config_templates.py`
- Test: `my_vocard_setup/tests/test_config_templates.py`

**Interfaces:**
- Consumes: `.env` keys `YT_CIPHER_HOST`, `YT_CIPHER_API_TOKEN`, `CLOUDFLARED_TOKEN`
- Produces: compose file with no forbidden secret fragments

- [ ] **Step 1: Write failing hardcode-absence / wiring tests**

Append:

```python
COMPOSE_FILE = SETUP_DIR / "docker-compose.yml"


def test_compose_has_no_forbidden_secrets():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text


def test_compose_wires_cipher_and_cloudflared_from_env():
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "YT_CIPHER_HOST" in text
    assert "YT_CIPHER_API_TOKEN" in text
    assert "CLOUDFLARED_TOKEN" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_compose_has_no_forbidden_secrets my_vocard_setup/tests/test_config_templates.py::test_compose_wires_cipher_and_cloudflared_from_env -v`

Expected: FAIL on forbidden fragments and/or missing env key names

- [ ] **Step 3: Update `docker-compose.yml`**

Replace ytcipher / cloudflared hardcodes. Target shape:

```yaml
  ytcipher:
    image: ghcr.io/kikkia/yt-cipher:master
    container_name: vocard-ytcipher
    restart: unless-stopped
    network_mode: host
    env_file:
      - .env
    environment:
      - HOST=${YT_CIPHER_HOST}
      - API_TOKEN=${YT_CIPHER_API_TOKEN}
      - OVERRIDE_PLAYER_VARIANT=IAS
      - MAX_THREADS=4

  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: vocard-cloudflared
    restart: unless-stopped
    network_mode: host
    env_file:
      - .env
    command: tunnel --no-autoupdate run --token ${CLOUDFLARED_TOKEN}
    depends_on:
      - dashboard
```

Leave other services unchanged except removing any of the forbidden fragments if present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_compose_has_no_forbidden_secrets my_vocard_setup/tests/test_config_templates.py::test_compose_wires_cipher_and_cloudflared_from_env -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/docker-compose.yml my_vocard_setup/tests/test_config_templates.py
git commit -m "fix(compose): load cipher and cloudflared secrets from env"
```

---

### Task 4: De-hardcode `lavalink/application.yml` + absence tests

**Files:**
- Modify: `my_vocard_setup/lavalink/application.yml`
- Modify: `my_vocard_setup/tests/test_config_templates.py`
- Test: `my_vocard_setup/tests/test_config_templates.py`

**Interfaces:**
- Consumes: `REMOTE_CIPHER_URL`, `YT_CIPHER_API_TOKEN`, `IP_BLOCKS`, existing `YOUTUBE_*` vars
- Produces: yml with env placeholders and no forbidden fragments

- [ ] **Step 1: Write failing tests**

Append:

```python
LAVALINK_YML = SETUP_DIR / "lavalink" / "application.yml"


def test_lavalink_yml_has_no_forbidden_secrets():
    text = LAVALINK_YML.read_text(encoding="utf-8")
    for fragment in FORBIDDEN_SECRET_FRAGMENTS:
        assert fragment not in text


def test_lavalink_yml_uses_env_placeholders():
    text = LAVALINK_YML.read_text(encoding="utf-8")
    assert "${REMOTE_CIPHER_URL" in text
    assert "${YT_CIPHER_API_TOKEN" in text
    assert "${IP_BLOCKS" in text
    assert "${YOUTUBE_OAUTH_REFRESH_TOKEN" in text
    assert "${YOUTUBE_POT_TOKEN" in text
    assert "${YOUTUBE_POT_VISITOR_DATA" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_lavalink_yml_has_no_forbidden_secrets my_vocard_setup/tests/test_config_templates.py::test_lavalink_yml_uses_env_placeholders -v`

Expected: FAIL (hardcoded URL/password/CIDR still present)

- [ ] **Step 3: Update `application.yml`**

Change these sections (keep surrounding structure):

```yaml
    remoteCipher:
      url: "${REMOTE_CIPHER_URL:}"
      password: "${YT_CIPHER_API_TOKEN:}"
      userAgent: "vocard"

    pot:
      token: "${YOUTUBE_POT_TOKEN:}"
      visitorData: "${YOUTUBE_POT_VISITOR_DATA:}"

    ratelimit:
      ipBlocks:
        - "${IP_BLOCKS:}"
```

And under `lavalink.server.ratelimit`:

```yaml
    ratelimit:
      ipBlocks:
        - "${IP_BLOCKS:}"
```

Keep `oauth.refreshToken: "${YOUTUBE_OAUTH_REFRESH_TOKEN:}"` as-is.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_lavalink_yml_has_no_forbidden_secrets my_vocard_setup/tests/test_config_templates.py::test_lavalink_yml_uses_env_placeholders -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/lavalink/application.yml my_vocard_setup/tests/test_config_templates.py
git commit -m "fix(lavalink): parameterize remoteCipher, password, and IP blocks"
```

---

### Task 5: Settings template load + Config env fallback tests

**Files:**
- Modify: `my_vocard_setup/tests/test_config_templates.py`
- Verify (no edit unless missing): `my_vocard_setup/settings Example.json`
- Test: `my_vocard_setup/tests/test_config_templates.py`

**Interfaces:**
- Consumes: `voicelink.config.Config`, `settings Example.json`
- Produces: passing load/fallback tests; settings file unchanged unless a required bot token key is missing (then add placeholder only)

- [ ] **Step 1: Write failing/pending load tests**

Append:

```python
import json
import os

import pytest

SETTINGS_EXAMPLE = SETUP_DIR / "settings Example.json"


def test_settings_example_has_bot_token_fields():
    data = json.loads(SETTINGS_EXAMPLE.read_text(encoding="utf-8"))
    assert "token" in data
    assert "client_id" in data
    assert "genius_token" in data
    nodes = data["nodes"]
    assert "tokens" in nodes["DEFAULT"]["yt_ratelimit"]
    assert isinstance(nodes["DEFAULT"]["yt_ratelimit"]["tokens"], list)
    # Spec: no new IP / YouTube-plugin settings keys
    assert "IP_PREFERENCE" not in data
    assert "YOUTUBE_OAUTH_REFRESH_TOKEN" not in data


def test_config_reads_token_fields_from_env_fallback(monkeypatch):
    monkeypatch.setenv("TOKEN", "env-bot-token")
    monkeypatch.setenv("CLIENT_ID", "123456789012345678")
    monkeypatch.setenv("GENIUS_TOKEN", "env-genius-token")
    monkeypatch.setenv("MONGODB_URL", "mongodb://localhost:27017")
    monkeypatch.setenv("MONGODB_NAME", "vocard_test")

    from voicelink.config import Config

    cfg = Config(
        {
            "token": "",
            "client_id": 0,
            "genius_token": "",
            "mongodb_url": "",
            "mongodb_name": "",
        }
    )
    assert cfg.token == "env-bot-token"
    assert cfg.client_id == 123456789012345678
    assert cfg.genius_token == "env-genius-token"
```

- [ ] **Step 2: Run tests**

Run: `pytest my_vocard_setup/tests/test_config_templates.py::test_settings_example_has_bot_token_fields my_vocard_setup/tests/test_config_templates.py::test_config_reads_token_fields_from_env_fallback -v`

Expected: PASS if settings already complete; if settings missing a key, FAIL then fix placeholders in Step 3. If Config singleton/`initialized` short-circuit causes stale values, reset by always constructing via `Config({...})` with a fresh settings dict (existing `__new__` replaces `_instance` when settings is not None). If `initialized` still blocks, set `cfg.initialized = False` pattern is wrong — instead construct a brand-new instance path only through `Config(settings_dict)`. If tests flake due to singleton, clear with:

```python
Config._instance = None
# then Config({...})
```

before construct (add only if needed after first failure).

- [ ] **Step 3: Fix settings template only if a test fails for missing keys**

Do **not** add IP/YouTube OAuth/POT fields. Only restore missing bot placeholders (`token`, `client_id`, `genius_token`, `yt_ratelimit.tokens`) if absent.

- [ ] **Step 4: Re-run Task 5 tests + full file**

Run: `pytest my_vocard_setup/tests/test_config_templates.py -v`

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/tests/test_config_templates.py
# include settings Example.json only if modified
git commit -m "test(config): cover settings template load and env fallbacks"
```

---

### Task 6: Full regression + post-implementation code review

**Files:**
- Review: all files touched in Tasks 1–5
- Test: entire pytest suite

**Interfaces:**
- Consumes: plan + `.superpower/specs/2026-08-11-env-hardcode-templates-design.md`
- Produces: review findings addressed (Critical/Important fixed)

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`

Expected: PASS (existing whitelist tests + new config template tests)

- [ ] **Step 2: Capture review SHAs**

```bash
BASE_SHA=$(git merge-base HEAD origin/main 2>/dev/null || git rev-parse 871b363)
# Prefer the commit immediately before Task 1 started if still on this branch:
# BASE_SHA=<sha of docs spec commit 871b363>
HEAD_SHA=$(git rev-parse HEAD)
echo BASE_SHA=$BASE_SHA
echo HEAD_SHA=$HEAD_SHA
```

Use `BASE_SHA=871b363` (spec commit) unless Task commits rebased; `HEAD_SHA` = current HEAD after Tasks 1–5.

- [ ] **Step 3: Dispatch code-reviewer subagent**

REQUIRED SUB-SKILL: `requesting-code-review`

Provide:
- DESCRIPTION: Removed compose/Lavalink hardcodes; added `.env.example`, `ip_preference` defaults, config template tests
- PLAN_OR_REQUIREMENTS: `.superpower/plans/2026-08-11-env-hardcode-templates.md` + `.superpower/specs/2026-08-11-env-hardcode-templates-design.md`
- BASE_SHA / HEAD_SHA from Step 2

- [ ] **Step 4: Fix Critical and Important findings**

Re-run affected tests after each fix:

Run: `pytest my_vocard_setup/tests/test_config_templates.py -v`

- [ ] **Step 5: Commit review fixes (if any) and final note**

```bash
git add -u
git commit -m "fix(config): address code review findings for env templates"
```

Skip empty commit if no fixes.

- [ ] **Step 6: Confirm definition of done**

Checklist:
- [ ] No forbidden secret fragments in compose/yml
- [ ] `.env.example` has all required keys
- [ ] Settings template has bot token fields only (no new IP keys)
- [ ] `pytest` green
- [ ] Code review Critical/Important resolved

---

## Self-Review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Create `.env.example` with §1.1 keys | Task 2 |
| Manual IP mapping table + no auto-detect | Task 1 (+ comments in Task 2) |
| Compose uses env for cipher host/token + Cloudflare | Task 3 |
| Lavalink remoteCipher/IP_BLOCKS/YouTube placeholders | Task 4 |
| Settings verify-only, no new IP/YT plugin keys | Task 5 |
| Config/template load tests | Tasks 1–5 |
| Post-implementation code review | Task 6 |
| Rotate previously leaked secrets (operator) | Called out in spec §5; remind in PR/review notes, not automated |

No TBD/placeholder steps remain in this plan.
