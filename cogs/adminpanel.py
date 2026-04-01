"""
cogs/adminpanel.py - /adminpanel slash command (server admins + DEV_USER_ID).
Guild-scoped only — all operations affect the current server exclusively.
"""

import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import DEV_USER_ID
from state import (
    active_dragonfest, active_dragonscales, raid_boss_active,
)

# Reuse modals from devpanel — they have no guild-switching logic
from cogs.devpanel import (
    _run,
    GiveCoinsAmountModal,
    GiveDragonsAmountModal,
    DragonFestModal,
    SpawnRaidModal,
    ResetUserModal,
    FixSoftlockModal,
    _DRAGON_OPTIONS,
    _PACK_OPTIONS,
    _MINUTES_OPTIONS,
)


def _is_admin(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == DEV_USER_ID
    )


def _main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Admin Panel",
        description="Manage your server. Select a category below.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🎁 Give",   value="Coins, packs, dragonscale, dragons, giveaway", inline=False)
    embed.add_field(name="🔄 Reset",  value="Quests, breed cooldown, adventure CD, bingo", inline=False)
    embed.add_field(name="⚔️ Spawn",  value="Dragonfest, raid boss, black market, kill raid", inline=False)
    embed.add_field(name="📊 Info",   value="Spawn status, raid info, fix softlock, clear events", inline=False)
    return embed


class AdminGiveCoinsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.send_modal(GiveCoinsAmountModal(self.bot, select.values[0]))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))


class AdminGiveDragonsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot
        self.selected_user = None
        self.selected_dragon = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select dragon type…", options=_DRAGON_OPTIONS, row=1)
    async def dragon_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_dragon = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Give", emoji="🐉", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_dragon:
            await interaction.response.send_message("❌ Select a user and dragon type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GiveDragonsAmountModal(self.bot, self.selected_user, self.selected_dragon))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))


class AdminGivePackModal(discord.ui.Modal, title="Give Pack"):
    amount = discord.ui.TextInput(label="Amount", placeholder="e.g. 3")

    def __init__(self, bot, guild_id: int, user, pack_type: str):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        self.pack_type = pack_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givepack',
                       [str(self.guild_id), str(self.user.id),
                        self.pack_type, self.amount.value])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class AdminGivePackView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_user = None
        self.selected_pack = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select pack type…", options=_PACK_OPTIONS, row=1)
    async def pack_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_pack = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Give", emoji="📦", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_pack:
            await interaction.response.send_message("❌ Select a user and pack type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            AdminGivePackModal(self.bot, self.guild_id, self.selected_user, self.selected_pack))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))


class AdminGiveDragonscaleView(discord.ui.View):
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.selected_user = None
        self.selected_minutes = None

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_user = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select duration…", options=_MINUTES_OPTIONS, row=1)
    async def minutes_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_minutes = int(select.values[0])
        await interaction.response.defer()

    @discord.ui.button(label="Give Dragonscale", emoji="🟪", style=discord.ButtonStyle.primary, row=2)
    async def give(self, interaction: discord.Interaction, _):
        if not self.selected_user or not self.selected_minutes:
            await interaction.response.send_message("❌ Select a user and duration first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('SELECT minutes FROM dragonscales WHERE guild_id = ? AND user_id = ?',
                      (self.guild_id, self.selected_user.id))
            row = c.fetchone()
            if row:
                c.execute('UPDATE dragonscales SET minutes = minutes + ? WHERE guild_id = ? AND user_id = ?',
                          (self.selected_minutes, self.guild_id, self.selected_user.id))
            else:
                c.execute('INSERT INTO dragonscales (guild_id, user_id, minutes) VALUES (?, ?, ?)',
                          (self.guild_id, self.selected_user.id, self.selected_minutes))
            conn.commit()
            conn.close()
            mins = self.selected_minutes
            label = f"{mins}m" if mins < 60 else f"{mins // 60}h" + (f" {mins % 60}m" if mins % 60 else "")
            await interaction.followup.send(
                f"✅ Gave **{label}** of Dragonscale 🟪 to {self.selected_user.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))


class AdminGiveView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Give Coins", emoji="🪙", style=discord.ButtonStyle.primary)
    async def give_coins(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🪙 Give Coins", color=discord.Color.gold()),
            view=AdminGiveCoinsView(self.bot))

    @discord.ui.button(label="Give Dragons", emoji="🐉", style=discord.ButtonStyle.primary)
    async def give_dragons(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🐉 Give Dragons", color=discord.Color.green()),
            view=AdminGiveDragonsView(self.bot))

    @discord.ui.button(label="Give Pack", emoji="📦", style=discord.ButtonStyle.primary)
    async def give_pack(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📦 Give Pack", color=discord.Color.blue()),
            view=AdminGivePackView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Give Dragonscale", emoji="🟪", style=discord.ButtonStyle.primary)
    async def give_dragonscale(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🟪 Give Dragonscale", color=discord.Color.purple()),
            view=AdminGiveDragonscaleView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Giveaway", emoji="🎁", style=discord.ButtonStyle.secondary)
    async def giveaway(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'giveaway', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))


class AdminResetView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Reset Quests", emoji="📋", style=discord.ButtonStyle.danger)
    async def reset_quests(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'resetquests', [])

    @discord.ui.button(label="Reset Breed CD", emoji="⏱️", style=discord.ButtonStyle.secondary)
    async def reset_breed_cd(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            ResetUserModal(self.bot, 'resetbreedcooldown', 'Reset Breed Cooldown'))

    @discord.ui.button(label="Reset Adventure CD", emoji="🗺️", style=discord.ButtonStyle.secondary)
    async def reset_adventure_cd(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            ResetUserModal(self.bot, 'resetadventurecd', 'Reset Adventure Cooldowns'))

    @discord.ui.button(label="Reset Bingo", emoji="🎯", style=discord.ButtonStyle.danger)
    async def reset_bingo(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'resetbingo', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))


class AdminSpawnView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Dragonfest", emoji="🎉", style=discord.ButtonStyle.primary)
    async def dragonfest(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(DragonFestModal(self.bot))

    @discord.ui.button(label="Spawn Raid Boss", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def spawn_raid(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(SpawnRaidModal(self.bot))

    @discord.ui.button(label="Spawn Black Market", emoji="🏴‍☠️", style=discord.ButtonStyle.primary)
    async def spawn_bm(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'spawnblackmarket', [])

    @discord.ui.button(label="Kill Raid Boss", emoji="💀", style=discord.ButtonStyle.danger)
    async def kill_raid(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'raidkill', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))


class AdminInfoView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Spawn Status", emoji="🔍", style=discord.ButtonStyle.secondary)
    async def spawn_status(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'spawnstatus', [])

    @discord.ui.button(label="Raid Info", emoji="⚔️", style=discord.ButtonStyle.secondary)
    async def raid_info(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'raidinfo', [])

    @discord.ui.button(label="Fix Softlock", emoji="🔓", style=discord.ButtonStyle.primary)
    async def fix_softlock(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(FixSoftlockModal(self.bot))

    @discord.ui.button(label="Clear Events", emoji="🧹", style=discord.ButtonStyle.danger)
    async def clear_events(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        current_time = int(time.time())
        try:
            active_dragonfest.pop(gid, None)
            active_dragonscales.pop(gid, None)
            raid_boss_active.pop(gid, None)

            conn = sqlite3.connect('dragon_bot.db', timeout=120.0)
            c = conn.cursor()
            c.execute('DELETE FROM dragonfest_stats WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM dragonscale_stats WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM raid_bosses WHERE guild_id = ?', (gid,))
            c.execute('DELETE FROM raid_damage WHERE guild_id = ?', (gid,))
            c.execute('UPDATE spawn_config SET last_spawn_time = ? WHERE guild_id = ?',
                      (current_time, gid))
            conn.commit()
            conn.close()

            await interaction.followup.send(
                "🧹 **Events cleared** for this server.\n"
                "✅ Dragonfest, dragonscale events, and raid boss removed.",
                ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=AdminPanelView(self.bot))


class AdminPanelView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=180)
        self.bot = bot

    @discord.ui.button(label="🎁 Give", style=discord.ButtonStyle.primary)
    async def give(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=AdminGiveView(self.bot))

    @discord.ui.button(label="🔄 Reset", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="🔄 Reset", color=discord.Color.orange()),
            view=AdminResetView(self.bot))

    @discord.ui.button(label="⚔️ Spawn", style=discord.ButtonStyle.primary)
    async def spawn(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="⚔️ Spawn", color=discord.Color.red()),
            view=AdminSpawnView(self.bot))

    @discord.ui.button(label="📊 Info", style=discord.ButtonStyle.secondary)
    async def info(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=discord.Embed(title="📊 Info", color=discord.Color.blue()),
            view=AdminInfoView(self.bot))


class AdminPanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="adminpanel", description="Server admin control panel")
    async def adminpanel(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("❌ Access denied.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_main_embed(), view=AdminPanelView(self.bot), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminPanelCog(bot))
