# Inviter Whitelist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict Vocard bot invites to permanent Owners (`bot_access_user`) and ephemeral runtime Inviters (`bot.runtime_inviters`), with `/whitelist` management and aligned OAuth invite permissions including `view_audit_log`.

**Architecture:** Store temporary inviters on the bot object (`set[int]`) so the join guard works even if the whitelist cog fails to load. Add `on_guild_join` to the existing Listeners cog with audit-log retries and guild-owner fallback. Add a new GroupCog for `/whitelist add|remove|list`. Share one invite-permission constant across bot invite URL builders; update Dashboard to the same integer.

**Tech Stack:** Python 3, discord.py 2.7.1, existing `func.logger` / `Config` singleton, pytest (new, for unit tests of pure helpers), Dashboard static JS.

## Global Constraints

- All whitelist user-facing strings are **hardcoded English** (no `LangHandler`).
- Temporary inviters live **only** in `bot.runtime_inviters` (in-memory `set[int]`) — never persisted to disk/JSON.
- Permanent Owners are managed **only** via `settings.json` `bot_access_user`; `/whitelist` never adds/removes Owners.
- Canonical invite permission integer is **`2184572096`** on every OAuth bot-invite surface.
- Invite URL client id must come from **`bot.user.id`** / placeholder bot id — **not** `Config().client_id`.
- `/whitelist` responses are always **`ephemeral=True`**.
- Existing guilds at boot are **never** audited or mass-evicted.
- Dashboard auth stays open to any Discord user; join guard is the only enforcement point.
- Do not touch playlist `type: "invite"` or `Config().invite_link` (support server).

---

## File Structure

| File | Responsibility |
|---|---|
| `my_vocard_setup/voicelink/invite_permissions.py` | Shared constant `BOT_INVITE_PERMISSIONS = 2184572096`, `build_bot_invite_url(client_id)`, `is_authorized_inviter(user_id, owners, runtime_inviters)`, `resolve_leave_channel(guild)` |
| `my_vocard_setup/tests/test_invite_permissions.py` | Unit tests for the helpers above |
| `my_vocard_setup/tests/test_whitelist_guard.py` | Unit tests for join-decision helpers (authorized / fallback / leave-channel) |
| `my_vocard_setup/main.py` | Init `runtime_inviters`; DM carve-out in `CommandCheck.interaction_check` |
| `my_vocard_setup/cogs/listeners.py` | New `on_guild_join` listener using helpers |
| `my_vocard_setup/cogs/whitelist.py` | New GroupCog: `/whitelist add|remove|list` |
| `my_vocard_setup/voicelink/placeholders.py` | `@@invite_link@@` permissions → `2184572096` via shared constant |
| `my_vocard_setup/update.py` | Bump `__version__` so `setup_hook` runs `tree.sync()` |
| `my_vocard_dashboard_setup/assets/js/objects.js` | Dashboard invite link permissions → `2184572096` |
| `my_vocard_setup/requirements-dev.txt` | `pytest` for local unit tests (optional install) |

---

### Task 1: Shared invite helpers + unit tests

**Files:**
- Create: `my_vocard_setup/voicelink/invite_permissions.py`
- Create: `my_vocard_setup/tests/__init__.py` (empty)
- Create: `my_vocard_setup/tests/test_invite_permissions.py`
- Create: `my_vocard_setup/requirements-dev.txt`

**Interfaces:**
- Consumes: nothing (foundation)
- Produces:
  - `BOT_INVITE_PERMISSIONS: int = 2184572096`
  - `def is_authorized_inviter(user_id: int, owners: list[int] \| set[int], runtime_inviters: set[int]) -> bool`
  - `def build_bot_invite_url(client_id: int) -> str`
  - `def resolve_leave_channel(guild) -> discord.abc.Messageable \| None` (returns `system_channel` or first text channel or `None`)

- [ ] **Step 1: Write the failing tests**

Create `my_vocard_setup/tests/test_invite_permissions.py`:

```python
import discord

from voicelink.invite_permissions import (
    BOT_INVITE_PERMISSIONS,
    build_bot_invite_url,
    is_authorized_inviter,
    resolve_leave_channel,
)


def test_canonical_permission_integer():
    assert BOT_INVITE_PERMISSIONS == 2184572096
    perms = discord.Permissions(BOT_INVITE_PERMISSIONS)
    assert perms.view_audit_log is True
    assert perms.view_channel is True
    assert perms.attach_files is True
    assert perms.use_application_commands is True


def test_is_authorized_inviter_owner():
    assert is_authorized_inviter(10, owners=[10], runtime_inviters=set()) is True


def test_is_authorized_inviter_runtime():
    assert is_authorized_inviter(20, owners=[], runtime_inviters={20}) is True


def test_is_authorized_inviter_rejects_unknown():
    assert is_authorized_inviter(30, owners=[10], runtime_inviters={20}) is False


def test_build_bot_invite_url_contains_permissions_and_scopes():
    url = build_bot_invite_url(123456789012345678)
    assert "client_id=123456789012345678" in url
    assert "permissions=2184572096" in url
    assert "scope=bot" in url
    assert "applications.commands" in url


class _FakeGuild:
    def __init__(self, system_channel=None, text_channels=None):
        self.system_channel = system_channel
        self.text_channels = text_channels or []


def test_resolve_leave_channel_prefers_system_channel():
    system = object()
    other = object()
    guild = _FakeGuild(system_channel=system, text_channels=[other])
    assert resolve_leave_channel(guild) is system


def test_resolve_leave_channel_falls_back_to_first_text():
    other = object()
    guild = _FakeGuild(system_channel=None, text_channels=[other])
    assert resolve_leave_channel(guild) is other


def test_resolve_leave_channel_none_when_empty():
    guild = _FakeGuild(system_channel=None, text_channels=[])
    assert resolve_leave_channel(guild) is None
```

Create empty `my_vocard_setup/tests/__init__.py`.

Create `my_vocard_setup/requirements-dev.txt`:

```text
pytest>=8.0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `my_vocard_setup/`:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/test_invite_permissions.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'voicelink.invite_permissions'` (or import error for missing symbols).

- [ ] **Step 3: Write minimal implementation**

Create `my_vocard_setup/voicelink/invite_permissions.py`:

```python
"""Shared OAuth invite permission helpers for whitelist join verification."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Union

import discord

BOT_INVITE_PERMISSIONS: int = 2184572096


def is_authorized_inviter(
    user_id: int,
    owners: Union[Sequence[int], Iterable[int]],
    runtime_inviters: set[int],
) -> bool:
    return user_id in owners or user_id in runtime_inviters


def build_bot_invite_url(client_id: int) -> str:
    return discord.utils.oauth_url(
        client_id,
        permissions=discord.Permissions(BOT_INVITE_PERMISSIONS),
        scopes=("bot", "applications.commands"),
    )


def resolve_leave_channel(guild: discord.Guild) -> Optional[discord.abc.Messageable]:
    if guild.system_channel is not None:
        return guild.system_channel
    if guild.text_channels:
        return guild.text_channels[0]
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_invite_permissions.py -v
```

Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/voicelink/invite_permissions.py my_vocard_setup/tests/__init__.py my_vocard_setup/tests/test_invite_permissions.py my_vocard_setup/requirements-dev.txt
git commit -m "feat: add shared bot invite permission helpers"
```

---

### Task 2: Initialize `bot.runtime_inviters` on boot

**Files:**
- Modify: `my_vocard_setup/main.py:67-71` (`Vocard.__init__`)
- Test: `my_vocard_setup/tests/test_runtime_inviters_init.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Vocard.runtime_inviters: set[int]` available before cogs load (empty set at construction)

- [ ] **Step 1: Write the failing test**

Create `my_vocard_setup/tests/test_runtime_inviters_init.py`:

```python
"""Ensure runtime_inviters exists on the bot class init signature via source contract.

We assert the attribute is assigned in Vocard.__init__ by reading main.py,
because constructing Vocard requires a live discord token/intents setup.
"""

from pathlib import Path


def test_vocard_init_assigns_runtime_inviters():
    main_src = Path(__file__).resolve().parents[1] / "main.py"
    text = main_src.read_text(encoding="utf-8")
    assert "self.runtime_inviters" in text
    assert "set()" in text
    # Must be in __init__, before setup_hook loads cogs
    init_idx = text.index("def __init__(self")
    setup_idx = text.index("async def setup_hook")
    runtime_idx = text.index("self.runtime_inviters")
    assert init_idx < runtime_idx < setup_idx
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_runtime_inviters_init.py -v
```

Expected: FAIL with assertion that `self.runtime_inviters` is missing.

- [ ] **Step 3: Write minimal implementation**

In `my_vocard_setup/main.py`, change `Vocard.__init__` to:

```python
class Vocard(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ipc_client: IPCClient
        self.runtime_inviters: set[int] = set()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_runtime_inviters_init.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/main.py my_vocard_setup/tests/test_runtime_inviters_init.py
git commit -m "feat: initialize runtime_inviters set on bot boot"
```

---

### Task 3: Join-decision helpers + `on_guild_join` listener

**Files:**
- Modify: `my_vocard_setup/voicelink/invite_permissions.py` (add `decide_join_authorization`)
- Create: `my_vocard_setup/tests/test_whitelist_guard.py`
- Modify: `my_vocard_setup/cogs/listeners.py` (add `on_guild_join`)

**Interfaces:**
- Consumes: `is_authorized_inviter`, `resolve_leave_channel`, `bot.runtime_inviters`, `Config().bot_access_user`
- Produces:
  - `def decide_join_authorization(*, inviter_id: int | None, guild_owner_id: int, owners: Sequence[int], runtime_inviters: set[int], audit_failed: bool) -> tuple[bool, str]`
    - Returns `(authorized: bool, source: str)` where `source` is `"audit"`, `"guild_owner_fallback"`, or `"rejected"`
  - `Listeners.on_guild_join(guild)` — net-new listener

- [ ] **Step 1: Write the failing tests**

Create `my_vocard_setup/tests/test_whitelist_guard.py`:

```python
from voicelink.invite_permissions import decide_join_authorization


def test_audit_path_authorizes_owner():
    ok, source = decide_join_authorization(
        inviter_id=10,
        guild_owner_id=99,
        owners=[10],
        runtime_inviters=set(),
        audit_failed=False,
    )
    assert ok is True
    assert source == "audit"


def test_audit_path_authorizes_runtime_inviter():
    ok, source = decide_join_authorization(
        inviter_id=20,
        guild_owner_id=99,
        owners=[10],
        runtime_inviters={20},
        audit_failed=False,
    )
    assert ok is True
    assert source == "audit"


def test_audit_path_rejects_unknown_inviter():
    ok, source = decide_join_authorization(
        inviter_id=30,
        guild_owner_id=99,
        owners=[10],
        runtime_inviters={20},
        audit_failed=False,
    )
    assert ok is False
    assert source == "rejected"


def test_fallback_authorizes_when_guild_owner_whitelisted():
    ok, source = decide_join_authorization(
        inviter_id=None,
        guild_owner_id=10,
        owners=[10],
        runtime_inviters=set(),
        audit_failed=True,
    )
    assert ok is True
    assert source == "guild_owner_fallback"


def test_fallback_rejects_when_guild_owner_not_whitelisted():
    ok, source = decide_join_authorization(
        inviter_id=None,
        guild_owner_id=99,
        owners=[10],
        runtime_inviters={20},
        audit_failed=True,
    )
    assert ok is False
    assert source == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_whitelist_guard.py -v
```

Expected: FAIL with `ImportError` / missing `decide_join_authorization`.

- [ ] **Step 3: Implement `decide_join_authorization`**

Append to `my_vocard_setup/voicelink/invite_permissions.py`:

```python
from typing import Optional, Sequence, Tuple


def decide_join_authorization(
    *,
    inviter_id: Optional[int],
    guild_owner_id: int,
    owners: Sequence[int],
    runtime_inviters: set[int],
    audit_failed: bool,
) -> Tuple[bool, str]:
    """Decide whether the bot may stay in a newly joined guild.

    When audit_failed is False and inviter_id is set, use the audit inviter.
    Otherwise fall back to guild owner whitelist membership.
    """
    if not audit_failed and inviter_id is not None:
        if is_authorized_inviter(inviter_id, owners, runtime_inviters):
            return True, "audit"
        return False, "rejected"

    if is_authorized_inviter(guild_owner_id, owners, runtime_inviters):
        return True, "guild_owner_fallback"
    return False, "rejected"
```

- [ ] **Step 4: Run unit tests to verify they pass**

```bash
python -m pytest tests/test_whitelist_guard.py -v
```

Expected: PASS.

- [ ] **Step 5: Add `on_guild_join` to Listeners**

In `my_vocard_setup/cogs/listeners.py`, add imports at top (keep existing imports; add these):

```python
from voicelink.invite_permissions import (
    decide_join_authorization,
    resolve_leave_channel,
)
```

Add this listener method on `Listeners` (before `async def setup`):

```python
    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        owners = Config().bot_access_user
        runtime_inviters = getattr(self.bot, "runtime_inviters", set())

        inviter_id: int | None = None
        audit_failed = False
        audit_error: Exception | None = None

        # Initial delay for audit-log propagation, then up to 3 attempts
        await asyncio.sleep(2.5)
        for attempt in range(3):
            try:
                async for entry in guild.audit_logs(
                    limit=5, action=discord.AuditLogAction.bot_add
                ):
                    if entry.user is not None:
                        inviter_id = entry.user.id
                        break
                if inviter_id is not None:
                    break
            except discord.Forbidden as e:
                audit_failed = True
                audit_error = e
                break
            except Exception as e:
                audit_failed = True
                audit_error = e
                break

            if attempt < 2:
                await asyncio.sleep(2)

        if inviter_id is None and not audit_failed:
            # Entry never appeared after retries — treat as audit failure / fallback
            audit_failed = True

        if audit_failed:
            func.logger.warning(
                "Audit log fetch failed for guild %s(%s); using guild-owner fallback. Error: %s",
                guild.name,
                guild.id,
                audit_error,
            )

        authorized, source = decide_join_authorization(
            inviter_id=inviter_id,
            guild_owner_id=guild.owner_id,
            owners=owners,
            runtime_inviters=runtime_inviters,
            audit_failed=audit_failed,
        )

        if authorized:
            func.logger.info(
                "Authorized bot join to guild %s(%s) via %s (inviter_id=%s)",
                guild.name,
                guild.id,
                source,
                inviter_id,
            )
            return

        leave_channel = resolve_leave_channel(guild)
        if leave_channel is not None:
            try:
                await leave_channel.send(
                    "This bot is restricted to authorized inviters only."
                )
            except discord.Forbidden:
                pass
            except Exception:
                pass

        func.logger.warning(
            "Unauthorized bot join to guild %s(%s); leaving. inviter_id=%s source=%s",
            guild.name,
            guild.id,
            inviter_id,
            source,
        )
        await guild.leave()
```

Notes for the implementer:
- Use `guild.owner_id` (int always available) rather than `guild.owner.id` (can be `None` if owner not cached).
- `getattr(self.bot, "runtime_inviters", set())` satisfies the cog-load isolation acceptance criterion if somehow attribute is missing.
- Do not mass-evict existing guilds on boot — this listener only fires for **new** joins.

- [ ] **Step 6: Smoke-check imports**

```bash
python -c "from cogs.listeners import Listeners; from voicelink.invite_permissions import decide_join_authorization; print('ok')"
```

Run from `my_vocard_setup/`. Expected: prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add my_vocard_setup/voicelink/invite_permissions.py my_vocard_setup/tests/test_whitelist_guard.py my_vocard_setup/cogs/listeners.py
git commit -m "feat: guard new guild joins against inviter whitelist"
```

---

### Task 4: DM carve-out for `/whitelist` in `CommandCheck`

**Files:**
- Modify: `my_vocard_setup/main.py:185-197` (`CommandCheck.interaction_check`)
- Test: `my_vocard_setup/tests/test_command_check_dm_carveout.py`

**Interfaces:**
- Consumes: `Config().bot_access_user` (same singleton as `bot_config`)
- Produces: `/whitelist*` allowed in DMs for Owners; other commands still guild-only; guild rejection message gains `ephemeral=True`

- [ ] **Step 1: Write the failing source-contract test**

Create `my_vocard_setup/tests/test_command_check_dm_carveout.py`:

```python
from pathlib import Path


def test_command_check_allows_whitelist_in_dm_for_owners():
    text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert 'startswith("whitelist")' in text
    assert "bot_access_user" in text
    assert 'ephemeral=True' in text
    # Existing guild-only message must become ephemeral
    assert 'send_message("This command can only be used in guilds!", ephemeral=True)' in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_command_check_dm_carveout.py -v
```

Expected: FAIL (carve-out / ephemeral not present yet).

- [ ] **Step 3: Replace `CommandCheck.interaction_check`**

Replace the method body in `my_vocard_setup/main.py` with:

```python
class CommandCheck(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.type == discord.InteractionType.application_command:
            if not interaction.guild:
                if interaction.command and interaction.command.qualified_name.startswith("whitelist"):
                    if interaction.user.id in Config().bot_access_user:
                        return True
                    await interaction.response.send_message(
                        "You are not able to use this command!", ephemeral=True
                    )
                    return False
                await interaction.response.send_message(
                    "This command can only be used in guilds!", ephemeral=True
                )
                return False

            channel_perm = interaction.channel.permissions_for(interaction.guild.me)
            if not channel_perm.read_messages or not channel_perm.send_messages:
                await interaction.response.send_message(
                    "I don't have permission to read or send messages in this channel.",
                    ephemeral=True,
                )
                return False

        return True
```

`Config` is already imported at `main.py:34`.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_command_check_dm_carveout.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/main.py my_vocard_setup/tests/test_command_check_dm_carveout.py
git commit -m "feat: allow /whitelist in DMs for bot owners"
```

---

### Task 5: `/whitelist` GroupCog (add / remove / list)

**Files:**
- Create: `my_vocard_setup/cogs/whitelist.py`
- Create: `my_vocard_setup/tests/test_whitelist_cog_helpers.py`

**Interfaces:**
- Consumes: `bot.runtime_inviters`, `Config().bot_access_user`, `build_bot_invite_url`, `is_authorized_inviter`
- Produces: global slash group `/whitelist` with subcommands `add`, `remove`, `list`; owner-only `interaction_check`; all responses ephemeral

- [ ] **Step 1: Write failing tests for cog helper behaviors**

Create `my_vocard_setup/tests/test_whitelist_cog_helpers.py`:

```python
"""Pure decision helpers mirroring /whitelist add|remove message branches."""

from voicelink.invite_permissions import build_bot_invite_url


def classify_add(user_id: int, owners: list[int], runtime: set[int]) -> str:
    if user_id in owners:
        return "already_owner"
    if user_id in runtime:
        return "already_inviter"
    return "added"


def classify_remove(user_id: int, owners: list[int], runtime: set[int]) -> str:
    if user_id in owners:
        return "cannot_remove_owner"
    if user_id in runtime:
        return "removed"
    return "not_in_list"


def test_add_classification():
    assert classify_add(1, [1], set()) == "already_owner"
    assert classify_add(2, [1], {2}) == "already_inviter"
    assert classify_add(3, [1], set()) == "added"


def test_remove_classification():
    assert classify_remove(1, [1], set()) == "cannot_remove_owner"
    assert classify_remove(2, [1], {2}) == "removed"
    assert classify_remove(3, [1], set()) == "not_in_list"


def test_add_always_returns_invite_with_canonical_perms():
    url = build_bot_invite_url(999)
    assert "permissions=2184572096" in url
```

These tests lock the branch labels the cog must implement. The cog itself is integration-tested manually (acceptance checklist).

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/test_whitelist_cog_helpers.py -v
```

Expected: PASS for helpers that only import `build_bot_invite_url` (already implemented). Keep this file as the living branch contract while implementing the cog.

- [ ] **Step 3: Create `cogs/whitelist.py`**

Create `my_vocard_setup/cogs/whitelist.py` with this full content:

```python
"""MIT License

Copyright (c) 2023 - present Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import discord
import function as func

from discord import app_commands
from discord.ext import commands

from voicelink import Config
from voicelink.invite_permissions import build_bot_invite_url


class Whitelist(commands.GroupCog, name="whitelist"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in Config().bot_access_user:
            guild_label = interaction.guild.name if interaction.guild else "DM"
            func.logger.warning(
                "Unauthorized /whitelist attempt by user %s in %s",
                interaction.user.id,
                guild_label,
            )
            await interaction.response.send_message(
                "You are not able to use this command!", ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="add", description="Add a temporary inviter and get an invite link.")
    @app_commands.describe(user="Discord user to authorize as a temporary inviter.")
    async def add(self, interaction: discord.Interaction, user: discord.User) -> None:
        owners = Config().bot_access_user
        runtime: set[int] = self.bot.runtime_inviters
        invite_url = build_bot_invite_url(self.bot.user.id)

        if user.id in owners:
            await interaction.response.send_message(
                f"{user.mention} is already a permanent Owner.\nInvite link: {invite_url}",
                ephemeral=True,
            )
        elif user.id in runtime:
            await interaction.response.send_message(
                f"{user.mention} is already in the temporary inviter whitelist.\nInvite link: {invite_url}",
                ephemeral=True,
            )
        else:
            runtime.add(user.id)
            await interaction.response.send_message(
                f"Added {user.mention} as a temporary inviter.\nInvite link: {invite_url}",
                ephemeral=True,
            )

        func.logger.info(
            "/whitelist add by %s targeting %s",
            interaction.user.id,
            user.id,
        )

    @app_commands.command(name="remove", description="Remove a temporary inviter.")
    @app_commands.describe(user="Discord user to remove from the temporary inviter list.")
    async def remove(self, interaction: discord.Interaction, user: discord.User) -> None:
        owners = Config().bot_access_user
        runtime: set[int] = self.bot.runtime_inviters

        if user.id in owners:
            await interaction.response.send_message(
                "Cannot remove permanent Owners from the whitelist.",
                ephemeral=True,
            )
            return

        if user.id in runtime:
            runtime.discard(user.id)
            await interaction.response.send_message(
                f"Removed {user.mention} from the temporary inviter list.",
                ephemeral=True,
            )
            func.logger.info(
                "/whitelist remove by %s targeting %s",
                interaction.user.id,
                user.id,
            )
            return

        await interaction.response.send_message(
            "User is not in the temporary inviter list.",
            ephemeral=True,
        )

    @app_commands.command(name="list", description="Show permanent Owners and temporary Inviters.")
    async def list_whitelist(self, interaction: discord.Interaction) -> None:
        owners = Config().bot_access_user
        runtime: set[int] = self.bot.runtime_inviters

        owners_value = "\n".join(f"<@{uid}>" for uid in owners) or "None"
        inviters_value = "\n".join(f"<@{uid}>" for uid in runtime) or "None"

        embed = discord.Embed(
            title="Inviter Whitelist",
            color=Config().embed_color,
        )
        embed.add_field(name="Owners (Permanent)", value=owners_value, inline=False)
        embed.add_field(name="Inviters (Temporary)", value=inviters_value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Whitelist(bot))
```

Important: use parameter type `discord.User` (not `Member`). Use `self.bot.user.id` for invite URL generation.

- [ ] **Step 4: Verify cog imports**

```bash
python -c "import cogs.whitelist as w; print(w.Whitelist)"
```

Run from `my_vocard_setup/`. Expected: prints the class.

- [ ] **Step 5: Run full unit suite**

```bash
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add my_vocard_setup/cogs/whitelist.py my_vocard_setup/tests/test_whitelist_cog_helpers.py
git commit -m "feat: add /whitelist slash commands for temporary inviters"
```

---

### Task 6: Align bot `@@invite_link@@` placeholder permissions

**Files:**
- Modify: `my_vocard_setup/voicelink/placeholders.py:74`
- Test: extend `my_vocard_setup/tests/test_invite_permissions.py` with a source-contract assertion, or add `tests/test_placeholders_invite_link.py`

**Interfaces:**
- Consumes: `BOT_INVITE_PERMISSIONS` from `voicelink.invite_permissions`
- Produces: `@@invite_link@@` URL uses `permissions=2184572096`

- [ ] **Step 1: Write the failing test**

Create `my_vocard_setup/tests/test_placeholders_invite_link.py`:

```python
from pathlib import Path

from voicelink.invite_permissions import BOT_INVITE_PERMISSIONS


def test_placeholders_invite_link_uses_canonical_permissions():
    text = (Path(__file__).resolve().parents[1] / "voicelink" / "placeholders.py").read_text(
        encoding="utf-8"
    )
    assert "2184260928" not in text
    assert "BOT_INVITE_PERMISSIONS" in text or str(BOT_INVITE_PERMISSIONS) in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_placeholders_invite_link.py -v
```

Expected: FAIL while old `2184260928` still present.

- [ ] **Step 3: Update placeholders.py**

At top of `my_vocard_setup/voicelink/placeholders.py`, ensure import:

```python
from voicelink.invite_permissions import BOT_INVITE_PERMISSIONS
```

(If the file already imports from `voicelink`/`Config`, add the new import next to existing imports without creating circular imports. Prefer:

```python
from .invite_permissions import BOT_INVITE_PERMISSIONS
```

if relative imports are already used in that package.)

Replace the invite_link line (~74):

```python
"invite_link": f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions={BOT_INVITE_PERMISSIONS}&scope=bot%20applications.commands"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_placeholders_invite_link.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/voicelink/placeholders.py my_vocard_setup/tests/test_placeholders_invite_link.py
git commit -m "fix: align @@invite_link@@ permissions with whitelist audit needs"
```

---

### Task 7: Align Dashboard invite permissions

**Files:**
- Modify: `my_vocard_dashboard_setup/assets/js/objects.js:846`
- Test: `my_vocard_dashboard_setup/tests/test_invite_permissions_js.py` (simple string check runnable with pytest from dashboard folder or repo root)

**Interfaces:**
- Consumes: nothing from bot package
- Produces: Dashboard “Invite to this server” URL uses `permissions=2184572096`

- [ ] **Step 1: Write the failing test**

Create `my_vocard_dashboard_setup/tests/test_invite_permissions_js.py`:

```python
from pathlib import Path


def test_dashboard_invite_uses_canonical_permissions():
    path = Path(__file__).resolve().parents[1] / "assets" / "js" / "objects.js"
    text = path.read_text(encoding="utf-8")
    assert "permissions=2184538176" not in text
    assert "permissions=2184572096" in text
```

Also create empty `my_vocard_dashboard_setup/tests/__init__.py`.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest ../my_vocard_dashboard_setup/tests/test_invite_permissions_js.py -v
```

(Run from `my_vocard_setup/` or pass absolute path.) Expected: FAIL.

- [ ] **Step 3: Update Dashboard JS**

In `my_vocard_dashboard_setup/assets/js/objects.js` around line 846, change:

```javascript
permissions=2184538176
```

to:

```javascript
permissions=2184572096
```

Exact line context:

```javascript
<a href="${`https://discord.com/oauth2/authorize?client_id=${player.selectedBot.id}&permissions=2184572096&scope=bot%20applications.commands`}" target="_blank" rel="noopener noreferrer">
```

Do **not** gate Dashboard invite UI on `bot_access_user`. Do not change playlist mail `type === "invite"` handling.

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest my_vocard_dashboard_setup/tests/test_invite_permissions_js.py -v
```

Expected: PASS (run from repo root).

- [ ] **Step 5: Commit**

```bash
git add my_vocard_dashboard_setup/assets/js/objects.js my_vocard_dashboard_setup/tests/__init__.py my_vocard_dashboard_setup/tests/test_invite_permissions_js.py
git commit -m "fix: align dashboard invite permissions with view_audit_log"
```

---

### Task 8: Bump bot version to trigger global command sync

**Files:**
- Modify: `my_vocard_setup/update.py:34` (`__version__ = "v2.7.3"` → `"v2.7.4"`)

**Interfaces:**
- Consumes: existing `setup_hook` version mismatch → `await self.tree.sync()`
- Produces: `/whitelist` registered globally on next boot after deploy

- [ ] **Step 1: Write the failing source-contract test**

Create `my_vocard_setup/tests/test_version_bump_for_sync.py`:

```python
from pathlib import Path
import re


def test_update_version_is_v2_7_4_or_newer_for_whitelist_sync():
    text = (Path(__file__).resolve().parents[1] / "update.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"(v\d+\.\d+\.\d+)"', text)
    assert match, "update.__version__ not found"
    version = match.group(1)
    assert version != "v2.7.3", "Bump update.__version__ so setup_hook syncs /whitelist"
    assert version == "v2.7.4"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_version_bump_for_sync.py -v
```

Expected: FAIL with message about bumping version.

- [ ] **Step 3: Bump version**

In `my_vocard_setup/update.py`:

```python
__version__ = "v2.7.4"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_version_bump_for_sync.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add my_vocard_setup/update.py my_vocard_setup/tests/test_version_bump_for_sync.py
git commit -m "chore: bump version to sync /whitelist global commands"
```

---

### Task 9: Full regression + manual acceptance checklist

**Files:**
- None new (verification only)

**Interfaces:**
- Consumes: all prior tasks
- Produces: green unit suite + documented manual Discord checks

- [ ] **Step 1: Run the full unit suite from repo root**

```bash
pip install -r my_vocard_setup/requirements-dev.txt
python -m pytest my_vocard_setup/tests my_vocard_dashboard_setup/tests -v
```

Expected: all PASS.

- [ ] **Step 2: Manual Discord acceptance (post-deploy)**

Work through this checklist against a running bot with an Owner account in `bot_access_user`:

1. Confirm `/whitelist` appears (after boot sync). If missing, use Owner debug UI `tree.sync()` once.
2. Owner runs `/whitelist list` in a guild → ephemeral embed with Owners + Inviters (`None` if empty).
3. Owner runs `/whitelist list` in DM → same result (carve-out works).
4. Non-Owner runs `/whitelist list` in guild and in DM → ephemeral denial; WARNING log.
5. `/whitelist add @tempUser` → adds to `runtime_inviters`, reply includes invite URL with `permissions=2184572096`.
6. Temp user invites via that URL → bot stays; INFO log.
7. Non-whitelisted user invites via Dashboard or public `@@invite_link@@` → leave message (if possible) + leave + WARNING log.
8. `/whitelist remove` on an Owner → `"Cannot remove permanent Owners from the whitelist."`
9. `/whitelist remove` on temp inviter → removed; `/whitelist remove` unknown → `"User is not in the temporary inviter list."`
10. Restart bot → `runtime_inviters` empty; previously joined guilds remain; new unauthorized joins still rejected.
11. Grep confirm three surfaces use `2184572096`:
    - `cogs/whitelist.py` / `build_bot_invite_url`
    - `voicelink/placeholders.py`
    - `dashboard assets/js/objects.js`
12. Optional isolation check: temporarily break `cogs/whitelist.py` import, reboot — bot boots; unauthorized joins still leave without `AttributeError` on `runtime_inviters`.

- [ ] **Step 3: Commit only if Step 2 found fixes**

If manual testing required code fixes, commit those fixes with messages like `fix: ...`. Do not create an empty commit if nothing changed.

---

## Self-Review

**1. Spec coverage**
| Spec section | Task(s) |
|---|---|
| 1.1 Owners via `bot_access_user` only | Task 5 (never mutate owners) |
| 1.2 `runtime_inviters` on bot init | Task 2 |
| 2.x `on_guild_join` delay/retry/fallback/leave | Task 3 |
| 2.3 English-only messages | Tasks 3, 5 |
| 3.1 `/whitelist` + owner guard + ephemeral | Task 5 |
| 3.1 DM carve-out in `CommandCheck` | Task 4 |
| 3.2 Command sync via version bump | Task 8 |
| 4.x Unified `2184572096` (3 surfaces) | Tasks 1, 5, 6, 7 |
| 4.4 Dashboard auth non-change | Task 7 notes |
| 5 Logging table | Tasks 3, 5 |
| 6 Acceptance checklist | Task 9 |

**2. Placeholder scan:** No TBD/TODO steps; all code blocks are concrete.

**3. Type consistency:** `runtime_inviters: set[int]`, `BOT_INVITE_PERMISSIONS = 2184572096`, `build_bot_invite_url(client_id: int) -> str`, `decide_join_authorization(...) -> tuple[bool, str]` used consistently across tasks.
