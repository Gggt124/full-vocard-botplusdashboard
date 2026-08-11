# Inviter Whitelist System Specification (Final Detailed Spec)

## Goal
Implement a dual-role inviter whitelist system for the Vocard Discord bot. The system restricts bot invitation into Discord servers strictly to authorized users, separating permanent **Owner** accounts from ephemeral **Inviter** accounts stored strictly in runtime memory.
**Key Features Include:**
- Adding temporary inviters at runtime with automated invite link generation.
- Viewing the active whitelist at runtime via slash commands.
- Removing temporary inviters at runtime via slash commands.
- Aligning **all** OAuth2 invite surfaces (slash command, Dashboard, bot embed placeholder) to one permission bitmask that includes `view_audit_log`.

---

## Affected Projects & Paths

This spec primarily targets the **Vocard Bot** but has a **required companion change** in the **Vocard Dashboard** (a separate project/repo).

| Project | Root Path | Scope of Change |
|---|---|---|
| **Vocard Bot** (primary) | `my_vocard_setup/` | New cog, modified listener, new runtime attribute, placeholder invite permission update, command sync |
| **Vocard Dashboard** (companion) | `my_vocard_dashboard_setup/` | Invite link permissions update only |

---

## 1. System Roles & Data Storage Architecture

### 1.1 Owner Role (Permanent)
- **Storage**: Persistent JSON configuration in `settings.json` under `bot_access_user`.
- **Permissions**:
  - Allowed to invite the bot to any Discord server.
  - Full authorization to execute `/whitelist` commands in Discord.
- **Persistence**: Permanent. Retained across container/server reboots.
- **How Owners are managed**: Edit `bot_access_user` in `settings.json` only. `/whitelist` never adds or removes permanent Owners.
- **Live-edit caveat**: `Config()` is a singleton (`voicelink/config.py:45-63`) instantiated once at boot. Editing `bot_access_user` in `settings.json` while the bot is running will **not** take effect until the bot is restarted. This is accepted behavior — Owner set changes are rare and a planned restart is expected.

### 1.2 Inviter Role (Ephemeral Runtime Storage)
- **Storage**: In-memory variable only (`bot.runtime_inviters` Python `set()`). No disk storage or JSON files required.
- **Initialization**: `self.runtime_inviters: set[int] = set()` in `Vocard.__init__()` in `main.py`, alongside `self.ipc_client`. This ensures the attribute is available before any cogs are loaded.
- **Permissions**:
  - Allowed to invite the bot into Discord servers while the current bot session is active.
  - Restricted from running `/whitelist` commands or managing whitelist entries.
- **Persistence**: **Cleared automatically on bot/container reboot**. Because it is stored entirely in memory, it naturally resets without needing explicit file cleanup.
- **Multi-process note**: `runtime_inviters` is per bot process. This deployment runs a single `vocard` bot container — no cross-process sync is required.
- **Cog-load isolation**: `runtime_inviters` lives on the `bot` object, **not** inside `cogs/whitelist.py`. `setup_hook` (`main.py:118-122`) catches per-cog load failures individually, so if `cogs/whitelist.py` ever fails to import, the join guard in `cogs/listeners.py` still has a valid `bot.runtime_inviters` (empty set) to read against and will function correctly.

---

## 2. Server Join Guard (`on_guild_join`)

> **Implementation note**: No `on_guild_join` listener exists in the codebase today (grep confirms zero matches across `my_vocard_setup/`). This is **net-new code** to add to the existing `Listeners` cog (`cogs/listeners.py`), which currently only defines `on_voicelink_*` and `on_voice_state_update` listeners.

### 2.1 Existing Guild Policy
- Existing servers where the bot is already present prior to bot startup are **exempt** and will not be audited or evicted on boot.
- **Note**: This means servers invited by a temporary inviter in a previous session will persist after reboot. The whitelist is a gate for **new invites only**, not a retroactive eviction mechanism.

### 2.2 Verification Flow for New Joins
When the bot is added to a new Discord guild (the new `on_guild_join` listener to be added to `cogs/listeners.py`):
1. **Delay & Retry for Audit Log Propagation**: Wait 2.5 seconds (`await asyncio.sleep(2.5)`) initially. If the `bot_add` event is not immediately found in the audit logs, implement a retry loop (e.g., 3 attempts, 2 seconds apart) to account for Discord API latency.
2. **Audit Log Inspection**: Query `guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add)`.
3. **Inviter Check**:
   - Match `entry.user.id` against `bot_access_user` OR `bot.runtime_inviters`.
   - **Fallback**: If no `bot_add` audit log entry is found after retries (or due to missing permissions like `discord.Forbidden`), fall back to checking whether `guild.owner.id` exists in the whitelist.
   - **Accepted False Negative**: If a whitelisted inviter (non-owner) invites the bot but the audit log fails, the guild owner fallback may incorrectly reject the join. This is accepted — safety over leniency. The inviter can re-invite with a link that includes `view_audit_log`.
   - **Fallback is the common path, not an edge case**: Even with `view_audit_log` baked into the invite permission integer, `guild.audit_logs()` frequently raises `discord.Forbidden` in real guilds (e.g. admins who tighten bot role permissions after the bot joins, or restrictive role hierarchies). Expect the guild-owner fallback to be the **primary** decision path in a meaningful fraction of joins, not a rare exception. Owners who are not the guild owner will be incorrectly rejected under this path — the only reliable workaround is a `view_audit_log`-bearing invite URL (Section 4) AND the inviter being the guild owner, OR the audit-log path succeeding.
4. **Outcome**:
   - **Authorized**: Bot stays in the server. Log: `INFO` with guild name, guild ID, and inviter info.
   - **Unauthorized**:
     - **Leave Message Channel Resolution**: Try `guild.system_channel` first → fallback to `guild.text_channels[0]` → skip message if no text channel exists.
     - Send message: `"This bot is restricted to authorized inviters only."` (Wrapped in a `try-except` block to ignore `discord.Forbidden` if the bot lacks messaging permissions).
     - Immediately call `await guild.leave()`.
     - Log: `WARNING` with guild name, guild ID, and unauthorized inviter info.
   - **Audit Log Fetch Failed**: Log `WARNING` indicating fallback was triggered, with guild info and error details.

### 2.3 Language Policy
All messages in the whitelist system (leave messages, command responses, error messages) are **hardcoded in English**. The `LangHandler` localization system is not used because:
- During `on_guild_join`, the bot does not yet know the guild's locale.
- `/whitelist` commands are owner-only and do not require per-guild localization.

---

## 3. Whitelist Management Interfaces

### 3.1 Discord Slash Command (`/whitelist`)
- **Location**: New cog `cogs/whitelist.py` (auto-loaded by `setup_hook` scanning `cogs/*.py`).
- **Scope**: Registered as a **global** slash command (available in all servers and DMs). Permission guard handles access control.
- **DM usage**: Allowed. Owners may run `/whitelist` in DMs. Parameter type `discord.User` works in DMs without requiring a shared guild.
- **Visibility**: **All responses are ephemeral** (`ephemeral=True`) — invite links and whitelist data are hidden from other users in the channel. (In DMs, ephemeral still applies to the interaction response.)
- **Permission Guard**: Executable **ONLY** by users in `Config().bot_access_user`. Returns ephemeral error message if run by unauthorized users. Follow the same pattern as `/debug` in `cogs/settings.py` (`cogs/settings.py:339-340`).

#### DM Availability — `CommandCheck.interaction_check` Carve-Out (REQUIRED)
The global command tree (`CommandCheck` in `main.py:185-197`) **rejects every application command invoked outside a guild**:

```python
# main.py:185-197 (existing, do not regress other commands)
class CommandCheck(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.type == discord.InteractionType.application_command:
            if not interaction.guild:
                await interaction.response.send_message("This command can only be used in guilds!")  # NOTE: no ephemeral=True
                return False
            ...
```

Without a change here, `/whitelist` **cannot run in DMs** — directly contradicting this section's DM requirement. Add a carve-out **before** the `not interaction.guild` branch so `/whitelist` (and only `/whitelist`) is allowed in DMs when the caller is an Owner:

```python
# main.py imports `Config` directly (main.py:34: `from voicelink import Config, ...`)
# and constructs the singleton as module-global `bot_config = Config(...)` (main.py:205).
# Either `Config().bot_access_user` or `bot_config.bot_access_user` works here — they are the same instance.
if not interaction.guild:
    if interaction.command and interaction.command.qualified_name.startswith("whitelist"):
        # Owners only — the cog's own permission guard still runs and will deny non-Owners.
        if interaction.user.id in Config().bot_access_user:
            return True
        await interaction.response.send_message("You are not able to use this command!", ephemeral=True)
        return False
    await interaction.response.send_message("This command can only be used in guilds!", ephemeral=True)
    return False
```

Notes:
- The cog-level permission guard (§3.1 Permission Guard) still runs after `interaction_check` returns `True`, so non-Owners invoking `/whitelist` in a DM are still denied — just via the cog instead of the tree.
- While editing this branch, opportunistically add `ephemeral=True` to the existing `"This command can only be used in guilds!"` response so the rejection is not broadcast to the channel. (Out of strict scope, but a one-token improvement.)

#### `/whitelist add <user>`
- **Parameter Type**: `discord.User` (not `discord.Member`) — allows adding users who are not in the current guild. Does not require `members` intent.
- **Behavior**:
  - If user is already a **permanent Owner** (`bot_access_user`): Reply with a notice that user is already a permanent Owner, but still generate and reply with the invite link.
  - If user is already in `bot.runtime_inviters`: Reply with a notice that user is already in the whitelist, and reply with the invite link.
  - Otherwise: Add user ID to `bot.runtime_inviters`, generate OAuth2 invite link, and reply with it.
- **Invite Link Generation**: Uses `discord.utils.oauth_url()` with `client_id` set to **`self.bot.user.id`** (always available in slash-command context, post-ready) and the **unified permission set** defined in Section 4. This mirrors the existing `@@invite_link@@` placeholder (`voicelink/placeholders.py:74`), which already uses `self.bot.user.id`.
  - **Do NOT use `Config().client_id`** as the source: `voicelink/config.py:79` falls back to `int(os.getenv("CLIENT_ID"))`, which raises `TypeError` when `CLIENT_ID` is unset (the env var is not required in the deployed container because `on_ready` overwrites `bot_config.client_id = self.user.id` at `main.py:150`). `bot.user.id` avoids this fragility entirely.
- **Logging**: `INFO` — who added whom.

#### `/whitelist remove <user>`
- **Parameter Type**: `discord.User`.
- **Behavior**:
  - If user is a **permanent Owner**: **Reject** with message `"Cannot remove permanent Owners from the whitelist."` — prevents Owner from thinking they successfully removed another Owner.
  - If user is in `bot.runtime_inviters`: Remove and confirm.
  - If user is not in either list: Reply with `"User is not in the temporary inviter list."`.
- **Logging**: `INFO` — who removed whom.

#### `/whitelist list`
- **Display Format**: Discord Embed with **2 separate fields**:
  - **Owners (Permanent)**: List of user mentions from `bot_access_user`. Always present.
  - **Inviters (Temporary)**: List of user mentions from `bot.runtime_inviters`, or `"None"` if empty.
- No pagination required (expected list size < 10).

### 3.2 Command Sync (Required for Deployment)
Global slash commands only appear after `bot.tree.sync()`.

In this codebase, `setup_hook` syncs the command tree **only when** `settings.json` `version` differs from `update.__version__` (see `main.py`). Therefore deployment of `/whitelist` requires **one** of:
1. **Preferred**: Bump `update.__version__` (or clear/change stored `version` so the mismatch triggers sync on next boot), **or**
2. Manually sync via the existing Owner-only debug UI (`tree.sync()`), **or**
3. Temporarily force a one-time `await self.tree.sync()` during rollout and remove after commands propagate.

Until sync completes, the join guard still works, but `/whitelist` will not be visible to Owners.

---

## 4. Unified Invite Permissions (All Surfaces)

Every OAuth2 bot-invite URL in the system **must** use the same permission integer so `on_guild_join` can read audit logs consistently.

### 4.1 Canonical Permission Set
| Permission | Required reason |
|---|---|
| `view_audit_log` | Whitelist join verification |
| `view_channel` | Read channel context |
| `send_messages` | Leave message + normal bot UX |
| `manage_messages` | Existing bot behavior |
| `embed_links` | Embeds |
| `attach_files` | File attachments |
| `read_message_history` | History reads |
| `use_external_emojis` | External emoji |
| `add_reactions` | Reactions |
| `connect` | Voice |
| `speak` | Voice |
| `use_voice_activation` / `use_vad` | Voice |
| `use_app_commands` | Slash command usage in guild |

**Canonical integer**: `2184572096`  
(= current Dashboard `2184538176` + `view_audit_log` `128` + `view_channel` `1024` + `attach_files` `32768`)

**Scopes** (unchanged): `bot applications.commands`

### 4.2 Surfaces That Must Use `2184572096`

| Surface | Project | File | Current value | Action |
|---|---|---|---|---|
| `/whitelist add` generated link | Bot | `cogs/whitelist.py` (new) | N/A | Build via `discord.utils.oauth_url(..., permissions=...)` matching the set above |
| Dashboard “Invite to this server” | Dashboard | `assets/js/objects.js` (~line 846) | `2184538176` | Replace with `2184572096` |
| Bot embed placeholder `@@invite_link@@` | Bot | `voicelink/placeholders.py` (~line 74) | `2184260928` | Replace with `2184572096` |

```diff
# Dashboard — assets/js/objects.js
-permissions=2184538176
+permissions=2184572096

# Bot — voicelink/placeholders.py
-permissions=2184260928
+permissions=2184572096
```

### 4.3 Why Alignment Matters
Without `view_audit_log` on **any** invite path:
1. `on_guild_join` → `guild.audit_logs(action=bot_add)` → `discord.Forbidden` (or missing entry).
2. Guard falls back to `guild.owner.id` whitelist check.
3. If the inviting Owner/Inviter is **not** the guild owner, the bot **incorrectly leaves**.

The public `@@invite_link@@` placeholder is especially important: it appears in help/settings embeds and is a real invite entry point today, not just Dashboard.

### 4.4 Dashboard Auth — Explicit Non-Change (Corrected)
Dashboard login is **Discord OAuth2 for any logged-in Discord user**. It does **not** gate on `bot_access_user`.

- `getMutualGuilds` / invite buttons remain available to any dashboard-authenticated user who has guilds the bot is not in.
- **Accepted UX**: A non-whitelisted user may click Invite in the Dashboard; the bot joins briefly, fails the whitelist check, sends the leave message, and leaves. Enforcement stays on the bot join guard, not the Dashboard UI.
- **Out of scope**: Restricting Dashboard invite UI to `bot_access_user` / `runtime_inviters`.
- **IPC routes / data format**: Unchanged. No IPC payloads expose `runtime_inviters`.
- **`settings.json` schema**: Unchanged. `bot_access_user` remains `list[int]`.

### 4.5 Out of Scope (Unrelated “invite” Features)
- Playlist share inbox items with `type: "invite"` in `cogs/playlist.py` / inbox views — these are playlist shares, not bot server invites.
- Support server link `Config().invite_link` (`server_invite_link` / Discord support guild) — not a bot OAuth invite.

---

## 5. Logging

All whitelist events are logged using `func.logger` (the existing logging infrastructure):

| Event | Level | Details |
|-------|-------|---------|
| Bot join — authorized | `INFO` | Guild name, guild ID, inviter user ID |
| Bot join — unauthorized + leave | `WARNING` | Guild name, guild ID, unauthorized inviter user ID |
| Audit log fetch failed (fallback) | `WARNING` | Guild name, guild ID, error details |
| `/whitelist add` executed | `INFO` | Executor user ID, target user ID |
| `/whitelist remove` executed | `INFO` | Executor user ID, target user ID |
| `/whitelist` permission denied | `WARNING` | Unauthorized user ID, guild name (or `"DM"` if no guild) |

---

## 6. Acceptance Criteria / Test Checklist

- [ ] Owner in `bot_access_user` invites via Dashboard link → bot stays; audit log path succeeds.
- [ ] Owner invites via `@@invite_link@@` / placeholder URL → bot stays; audit log path succeeds.
- [ ] `/whitelist add <user>` adds to `runtime_inviters` and returns invite URL with permissions `2184572096`.
- [ ] Temporary inviter uses that URL → bot stays while session is alive.
- [ ] Non-whitelisted user invites (Dashboard or public link) → leave message (if possible) + `guild.leave()` + WARNING log.
- [ ] `/whitelist remove` cannot remove Owners; removes temp inviters; reports missing users correctly.
- [ ] `/whitelist list` shows Owners + Inviters (or `"None"`).
- [ ] Non-Owner running `/whitelist` gets ephemeral denial.
- [ ] `/whitelist` works in DM for an Owner. **Verify the `CommandCheck.interaction_check` carve-out (`main.py:185-197`) is in place** — without it, the global `not interaction.guild` branch blocks the command with `"This command can only be used in guilds!"`.
- [ ] Non-Owner invoking `/whitelist` in a DM is denied (by either the carve-out or the cog-level guard) — does **not** execute the command.
- [ ] If `cogs/whitelist.py` fails to load (simulated import error), the bot still boots and `on_guild_join` in `cogs/listeners.py` reads `bot.runtime_inviters` (empty set) without `AttributeError`; new unauthorized joins are still rejected.
- [ ] Bot reboot clears `runtime_inviters`; previously joined guilds are **not** mass-evicted.
- [ ] After deploy, `/whitelist` is visible (command sync completed via version bump or manual sync).
- [ ] All three invite surfaces use `permissions=2184572096`.

---

## 7. Summary of Edge Cases & UX Resolved
- **Reboot Cleansing**: Temporary inviters use an in-memory set, naturally clearing on reboot without disk cleanup or file I/O overhead. Servers invited by temp inviters persist (by design — whitelist gates new invites only).
- **Audit Log Delays & API Latency**: Retry loop (3 attempts, 2s apart) + Guild Owner fallback. False negatives from fallback are accepted; correct invite links with `view_audit_log` minimize them.
- **Error Resilient Leave**: `try-except` on leave messages with channel resolution fallback (`system_channel` → `text_channels[0]` → skip).
- **Role Isolation**: Only Owners can modify whitelist; Inviters can only invite.
- **Unified Invite Permissions**: `/whitelist add`, Dashboard, and `placeholders.py` all use `2184572096`.
- **Duplicate & Overlap Handling**: Adding existing Owners or duplicate Inviters is handled gracefully with informative messages and invite link generation.
- **Owner Protection**: `/whitelist remove` explicitly rejects attempts to remove permanent Owners.
- **Privacy**: All `/whitelist` responses are ephemeral.
- **Global + DM Availability**: `/whitelist` is a global command usable in guilds and DMs, guarded by `bot_access_user`.
- **No Extra Intents Required**: Uses `discord.User` parameter type, avoiding `members` intent.
- **Dashboard Auth Reality**: Dashboard is not Owner-gated; join guard is the enforcement point for unauthorized invites.
- **Command Sync**: Deploy must trigger `tree.sync()` (version bump or manual) so `/whitelist` appears.
