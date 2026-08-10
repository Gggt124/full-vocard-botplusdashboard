# Inviter Whitelist System Specification (Final Detailed Spec)

## Goal
Implement a dual-role inviter whitelist system for the Vocard Discord bot. The system restricts bot invitation into Discord servers strictly to authorized users, separating permanent **Owner** accounts from ephemeral **Inviter** accounts stored strictly in runtime memory.
**Key Features Include:**
- Adding temporary inviters at runtime with automated invite link generation.
- Viewing the active whitelist at runtime via slash commands.
- Removing temporary inviters at runtime via slash commands.

---

## Affected Projects & Paths

This spec primarily targets the **Vocard Bot** but has a **required companion change** in the **Vocard Dashboard** (a separate project/repo).

| Project | Root Path | Scope of Change |
|---|---|---|
| **Vocard Bot** (primary) | `my_vocard_setup/my_vocard_setup/` | New cog, modified listener, new runtime attribute |
| **Vocard Dashboard** (companion) | `my_vocard_dashboard_setup/my_vocard_dashboard_setup/` | Invite link permissions update only |

---

## 1. System Roles & Data Storage Architecture

### 1.1 Owner Role (Permanent)
- **Storage**: Persistent JSON configuration in `settings.json` under `bot_access_user`.
- **Permissions**:
  - Allowed to invite the bot to any Discord server.
  - Full authorization to execute `/whitelist` commands in Discord.
- **Persistence**: Permanent. Retained across container/server reboots.

### 1.2 Inviter Role (Ephemeral Runtime Storage)
- **Storage**: In-memory variable only (`bot.runtime_inviters` Python `set()`). No disk storage or JSON files required.
- **Initialization**: `self.runtime_inviters: set[int] = set()` in `Vocard.__init__()` in `main.py`, alongside `self.ipc_client`. This ensures the attribute is available before any cogs are loaded.
- **Permissions**:
  - Allowed to invite the bot into Discord servers while the current bot session is active.
  - Restricted from running `/whitelist` commands or managing whitelist entries.
- **Persistence**: **Cleared automatically on bot/container reboot**. Because it is stored entirely in memory, it naturally resets without needing explicit file cleanup.

---

## 2. Server Join Guard (`on_guild_join`)

### 2.1 Existing Guild Policy
- Existing servers where the bot is already present prior to bot startup are **exempt** and will not be audited or evicted on boot.
- **Note**: This means servers invited by a temporary inviter in a previous session will persist after reboot. The whitelist is a gate for **new invites only**, not a retroactive eviction mechanism.

### 2.2 Verification Flow for New Joins
When the bot is added to a new Discord guild (`on_guild_join` listener in `cogs/listeners.py`):
1. **Delay & Retry for Audit Log Propagation**: Wait 2.5 seconds (`await asyncio.sleep(2.5)`) initially. If the `bot_add` event is not immediately found in the audit logs, implement a retry loop (e.g., 3 attempts, 2 seconds apart) to account for Discord API latency.
2. **Audit Log Inspection**: Query `guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add)`.
3. **Inviter Check**:
   - Match `entry.user.id` against `bot_access_user` OR `bot.runtime_inviters`.
   - **Fallback**: If no `bot_add` audit log entry is found after retries (or due to missing permissions like `discord.Forbidden`), fall back to checking whether `guild.owner.id` exists in the whitelist.
   - **Accepted False Negative**: If a whitelisted inviter (non-owner) invites the bot but the audit log fails, the guild owner fallback may incorrectly reject the join. This is accepted — safety over leniency. The inviter can re-invite.
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
- **Location**: New cog `cogs/whitelist.py`.
- **Scope**: Registered as a **global** slash command (available in all servers). Permission guard handles access control.
- **Visibility**: **All responses are ephemeral** (`ephemeral=True`) — invite links and whitelist data are hidden from other users in the channel.
- **Subcommands**:

#### `/whitelist add <user>`
- **Parameter Type**: `discord.User` (not `discord.Member`) — allows adding users who are not in the current guild. Does not require `members` intent.
- **Behavior**:
  - If user is already a **permanent Owner** (`bot_access_user`): Reply with a notice that user is already a permanent Owner, but still generate and reply with the invite link.
  - If user is already in `bot.runtime_inviters`: Reply with a notice that user is already in the whitelist, and reply with the invite link.
  - Otherwise: Add user ID to `bot.runtime_inviters`, generate OAuth2 invite link, and reply with it.
- **Invite Link Generation**: Uses `discord.utils.oauth_url()` with `client_id` from `Config().client_id` and the following `discord.Permissions`:
  - `view_audit_log` (required for whitelist verification)
  - `view_channel`
  - `send_messages`
  - `manage_messages`
  - `embed_links`
  - `attach_files`
  - `read_message_history`
  - `use_external_emojis`
  - `add_reactions`
  - `connect`
  - `speak`
  - `use_voice_activation`
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

- **Permission Guard**: Executable **ONLY** by users in `bot_access_user`. Returns ephemeral error message if run by unauthorized users.

---

## 4. Dashboard Invite Link — Required Permission Update

**Project**: Vocard Dashboard (`my_vocard_dashboard_setup/my_vocard_dashboard_setup/`)

The Dashboard has an "Invite the Bot to Your Server" feature that generates an OAuth2 invite link on the frontend. This link **must include `view_audit_log`** permission for the whitelist guard (`on_guild_join`) to function correctly.

### 4.1 Current State (Before This Spec)
- **File**: `assets/js/objects.js` (line 846)
- **Current permissions value**: `2184538176`
- **Missing permission**: `view_audit_log` (bit 7, value 128)

### 4.2 Required Change
- **New permissions value**: `2184538304` (`2184538176 + 128`)
- **Change location**: `assets/js/objects.js` line 846 — the OAuth2 authorize URL in the `getMutualGuilds` method.

```diff
-https://discord.com/oauth2/authorize?client_id=${player.selectedBot.id}&permissions=2184538176&scope=bot%20applications.commands
+https://discord.com/oauth2/authorize?client_id=${player.selectedBot.id}&permissions=2184538304&scope=bot%20applications.commands
```

### 4.3 Why This Is Required
Without `view_audit_log`, bots invited via the Dashboard will lack permission to read audit logs in the target guild. This triggers the following failure cascade:
1. `on_guild_join` fires → attempts `guild.audit_logs(action=bot_add)` → raises `discord.Forbidden`.
2. Guard falls back to checking `guild.owner.id` against the whitelist.
3. If the guild owner is **not** in `bot_access_user` or `runtime_inviters` (common — the inviter is an Owner, but the guild owner is a different person), the bot **incorrectly leaves** the server.

### 4.4 No Other Dashboard Changes Required
- **IPC routes / data format**: Unchanged. The Dashboard communicates with the bot via WebSocket IPC (`/ws_bot`). No IPC payloads are modified by this spec.
- **`settings.json` schema**: Unchanged. `bot_access_user` remains `list[int]`.
- **Dashboard authentication**: Unchanged. Dashboard still uses Discord OAuth2 + `bot_access_user` for admin access.
- **`runtime_inviters`**: Stored in bot memory only — never sent to the Dashboard, never exposed via IPC.

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
| `/whitelist` permission denied | `WARNING` | Unauthorized user ID, guild name |

---

## 6. Summary of Edge Cases & UX Resolved
- **Reboot Cleansing**: Temporary inviters use an in-memory set, naturally clearing on reboot without disk cleanup or file I/O overhead. Servers invited by temp inviters persist (by design — whitelist gates new invites only).
- **Audit Log Delays & API Latency**: Implemented a retry loop (3 attempts, 2s apart) + Guild Owner fallback to prevent premature kicks. False negatives from fallback are accepted.
- **Error Resilient Leave**: Uses `try-except` on leave messages with channel resolution fallback (`system_channel` → `text_channels[0]` → skip).
- **Role Isolation**: Only Owners can modify whitelist; Inviters can only invite.
- **Automated & Dynamic Invite Links**: `/whitelist add` dynamically generates OAuth2 links with explicit `discord.Permissions`, including `view_audit_log`.
- **Duplicate & Overlap Handling**: Adding existing Owners or duplicate Inviters is handled gracefully with informative messages and invite link generation.
- **Owner Protection**: `/whitelist remove` explicitly rejects attempts to remove permanent Owners.
- **Privacy**: All `/whitelist` responses are ephemeral — invite links and user lists are not visible to other users.
- **Global Availability**: `/whitelist` is a global command accessible from any server, guarded by `bot_access_user` permission check.
- **No Extra Intents Required**: Uses `discord.User` parameter type, avoiding the need for `members` intent.
- **Dashboard Invite Link Compatibility**: The Dashboard's frontend invite link (`assets/js/objects.js`) must be updated to include `view_audit_log` permission (`2184538176` → `2184538304`). Without this, bots invited via the Dashboard may be incorrectly evicted by the `on_guild_join` guard. See Section 4 for details.
