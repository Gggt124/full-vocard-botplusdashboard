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
