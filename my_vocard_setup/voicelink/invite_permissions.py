"""Shared OAuth invite permission helpers for whitelist join verification."""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple, Union

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


def classify_whitelist_add(
    user_id: int,
    owners: Sequence[int],
    runtime_inviters: set[int],
) -> str:
    if user_id in owners:
        return "already_owner"
    if user_id in runtime_inviters:
        return "already_inviter"
    return "added"


def classify_whitelist_remove(
    user_id: int,
    owners: Sequence[int],
    runtime_inviters: set[int],
) -> str:
    if user_id in owners:
        return "cannot_remove_owner"
    if user_id in runtime_inviters:
        return "removed"
    return "not_in_list"

