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


import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cogs.listeners import Listeners


class AsyncIter:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        self.iter = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self.iter)
        except StopIteration:
            raise StopAsyncIteration


def test_on_guild_join_filters_by_target_bot_id():
    async def _run():
        bot = MagicMock()
        bot.user.id = 12345
        bot.runtime_inviters = set()

        listeners = Listeners.__new__(Listeners)
        listeners.bot = bot

        target_wrong = MagicMock(id=99999)
        target_right = MagicMock(id=12345)

        entry_other_bot = MagicMock()
        entry_other_bot.user = MagicMock(id=500)
        entry_other_bot.target = target_wrong

        entry_our_bot = MagicMock()
        entry_our_bot.user = MagicMock(id=600)
        entry_our_bot.target = target_right

        guild = MagicMock()
        guild.name = "TestGuild"
        guild.id = 111
        guild.owner_id = 999
        guild.audit_logs.return_value = AsyncIter([entry_other_bot, entry_our_bot])
        guild.leave = AsyncMock()

        with patch("asyncio.sleep", AsyncMock()), \
             patch("cogs.listeners.Config") as mock_config, \
             patch("cogs.listeners.decide_join_authorization") as mock_decide:
            mock_config.return_value.bot_access_user = [600]
            mock_decide.return_value = (True, "audit")

            await listeners.on_guild_join(guild)

            mock_decide.assert_called_once_with(
                inviter_id=600,
                guild_owner_id=999,
                owners=[600],
                runtime_inviters=set(),
                audit_failed=False,
            )

    asyncio.run(_run())


def test_on_guild_join_logs_clear_warning_on_audit_timeout():
    async def _run():
        bot = MagicMock()
        bot.user.id = 12345
        bot.runtime_inviters = set()

        listeners = Listeners.__new__(Listeners)
        listeners.bot = bot

        guild = MagicMock()
        guild.name = "TestGuild"
        guild.id = 111
        guild.owner_id = 999
        guild.audit_logs.return_value = AsyncIter([])
        guild.system_channel = None
        guild.text_channels = []
        guild.leave = AsyncMock()

        with patch("asyncio.sleep", AsyncMock()), \
             patch("cogs.listeners.Config") as mock_config, \
             patch("cogs.listeners.func.logger.warning") as mock_warning, \
             patch("cogs.listeners.decide_join_authorization") as mock_decide:
            mock_config.return_value.bot_access_user = [100]
            mock_decide.return_value = (False, "rejected")

            await listeners.on_guild_join(guild)

            mock_warning.assert_any_call(
                "Audit log fetch failed for guild %s(%s); using guild-owner fallback. Error: %s",
                "TestGuild",
                111,
                "Log entry not found after retries",
            )
            guild.leave.assert_awaited_once()

    asyncio.run(_run())


def test_on_guild_join_unauthorized_sends_leave_message_then_leaves():
    async def _run():
        bot = MagicMock()
        bot.user.id = 12345
        bot.runtime_inviters = set()

        listeners = Listeners.__new__(Listeners)
        listeners.bot = bot

        leave_channel = MagicMock()
        leave_channel.send = AsyncMock()

        guild = MagicMock()
        guild.name = "TestGuild"
        guild.id = 111
        guild.owner_id = 999
        guild.audit_logs.return_value = AsyncIter([])
        guild.system_channel = leave_channel
        guild.text_channels = []
        guild.leave = AsyncMock()

        with patch("asyncio.sleep", AsyncMock()), \
             patch("cogs.listeners.Config") as mock_config, \
             patch("cogs.listeners.decide_join_authorization") as mock_decide:
            mock_config.return_value.bot_access_user = [100]
            mock_decide.return_value = (False, "rejected")

            await listeners.on_guild_join(guild)

            leave_channel.send.assert_awaited_once_with(
                "This bot is restricted to authorized inviters only."
            )
            guild.leave.assert_awaited_once()

    asyncio.run(_run())
