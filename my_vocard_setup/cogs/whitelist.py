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
from voicelink.invite_permissions import (
    build_bot_invite_url,
    classify_whitelist_add,
    classify_whitelist_remove,
)


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
        action = classify_whitelist_add(user.id, owners, runtime)

        if action == "already_owner":
            await interaction.response.send_message(
                f"{user.mention} is already a permanent Owner.\nInvite link: {invite_url}",
                ephemeral=True,
            )
        elif action == "already_inviter":
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
        action = classify_whitelist_remove(user.id, owners, runtime)

        if action == "cannot_remove_owner":
            await interaction.response.send_message(
                "Cannot remove permanent Owners from the whitelist.",
                ephemeral=True,
            )
            return

        if action == "removed":
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
