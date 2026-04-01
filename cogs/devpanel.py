"""
cogs/devpanel.py - /devpanel slash command (DEV_USER_ID only).
Replaces all -db prefix commands with an interactive panel.
"""

import sqlite3
import time

import discord
from discord import app_commands
from discord.ext import commands

from config import DEV_USER_ID, DRAGON_TYPES, PACK_TYPES

# ── Select options (built once at import time) ────────────────────────────────
_DRAGON_OPTIONS = [
    discord.SelectOption(label=data['name'], value=key, description=key)
    for key, data in list(DRAGON_TYPES.items())[:25]
]
_PACK_OPTIONS = [
    discord.SelectOption(label=data['name'], value=key)
    for key, data in PACK_TYPES.items()
]
_MINUTES_OPTIONS = [
    discord.SelectOption(label="5 minutes",   value="5"),
    discord.SelectOption(label="10 minutes",  value="10"),
    discord.SelectOption(label="15 minutes",  value="15"),
    discord.SelectOption(label="30 minutes",  value="30"),
    discord.SelectOption(label="1 hour",      value="60"),
    discord.SelectOption(label="2 hours",     value="120"),
    discord.SelectOption(label="3 hours",     value="180"),
    discord.SelectOption(label="6 hours",     value="360"),
    discord.SelectOption(label="12 hours",    value="720"),
    discord.SelectOption(label="24 hours",    value="1440"),
]
_STATUS_OPTIONS = [
    discord.SelectOption(label="🟢 Online",          value="online"),
    discord.SelectOption(label="🟡 Idle",             value="idle"),
    discord.SelectOption(label="🔴 Do Not Disturb",   value="dnd"),
    discord.SelectOption(label="⚫ Invisible",         value="invisible"),
]
_ACTIVITY_OPTIONS = [
    discord.SelectOption(label="❌ No Activity",   value="none"),
    discord.SelectOption(label="🎮 Playing",       value="playing"),
    discord.SelectOption(label="👀 Watching",      value="watching"),
    discord.SelectOption(label="🎵 Listening",     value="listening"),
    discord.SelectOption(label="📡 Streaming",     value="streaming"),
]


# ── Fake message adapter so we can reuse handle_dev_command ─────────────────

class _FakeChannel:
    """Collects send() calls and forwards them as ephemeral followups."""
    def __init__(self, interaction: discord.Interaction):
        self._interaction = interaction

    async def send(self, content=None, embed=None, view=None, **kwargs):
        try:
            if embed:
                await self._interaction.followup.send(embed=embed, view=view, ephemeral=True)
            elif content:
                await self._interaction.followup.send(str(content), ephemeral=True)
        except Exception:
            pass


class FakeMessage:
    """Wraps an interaction + resolved users so handle_dev_command can run unchanged."""
    def __init__(self, interaction: discord.Interaction, bot: commands.Bot,
                 mentions: list[discord.User] | None = None):
        self.guild   = interaction.guild
        self.channel = _FakeChannel(interaction)
        self.author  = interaction.user
        self.mentions = mentions or []
        self._state  = bot._connection
        self.client  = bot

    async def _resolve_user(self, bot: commands.Bot, user_id: int) -> discord.User | None:
        try:
            return bot.get_user(user_id) or await bot.fetch_user(user_id)
        except Exception:
            return None


async def _run(interaction: discord.Interaction, bot: commands.Bot,
               command: str, args: list[str],
               mentions: list[discord.User] | None = None):
    """Build FakeMessage and call handle_dev_command."""
    from cogs.admin import handle_dev_command
    msg = FakeMessage(interaction, bot, mentions)
    await handle_dev_command(msg, command, args)


# ── Modals ────────────────────────────────────────────────────────────────────

class _ChangeGuildModal(discord.ui.Modal, title="Change Guild ID"):
    guild_id = discord.ui.TextInput(label="Guild ID", placeholder="123456789012345678")

    def __init__(self, parent_view):
        super().__init__()
        self._parent = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self._parent.guild_id = int(self.guild_id.value)
            await interaction.response.send_message(
                f"✅ Guild set to `{self._parent.guild_id}`", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Invalid Guild ID", ephemeral=True)


class GiveCoinsAmountModal(discord.ui.Modal, title="Give Coins"):
    amount = discord.ui.TextInput(label="Amount", placeholder="e.g. 10000")

    def __init__(self, bot, user):
        super().__init__()
        self.bot = bot
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givecoins',
                       [self.amount.value], mentions=[self.user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class GiveDragonsAmountModal(discord.ui.Modal, title="Give Dragons"):
    amount = discord.ui.TextInput(label="Amount (or * for all types)", placeholder="e.g. 5")

    def __init__(self, bot, user, dragon_type):
        super().__init__()
        self.bot = bot
        self.user = user
        self.dragon_type = dragon_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givedragons',
                       [self.dragon_type, self.amount.value], mentions=[self.user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class GivePackAmountModal(discord.ui.Modal, title="Give Pack"):
    amount = discord.ui.TextInput(label="Amount", placeholder="e.g. 3")

    def __init__(self, bot, guild_id, user, pack_type):
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


class GrantPassLevelsModal(discord.ui.Modal, title="Grant Dragonpass Level"):
    levels = discord.ui.TextInput(label="Levels to grant", placeholder="e.g. 5")

    def __init__(self, bot, user):
        super().__init__()
        self.bot = bot
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'passgrant',
                       [self.levels.value], mentions=[self.user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class ResetUserModal(discord.ui.Modal):
    user_id = discord.ui.TextInput(label="User ID (or * for all)", placeholder="123456789012345678 or *")

    def __init__(self, bot, command: str, title_: str):
        super().__init__(title=title_)
        self.bot = bot
        self._command = command

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = self.user_id.value.strip()
            if val == '*':
                await _run(interaction, self.bot, self._command, ['*'])
            else:
                user = await self.bot.fetch_user(int(val))
                await _run(interaction, self.bot, self._command, [], mentions=[user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class DragonFestModal(discord.ui.Modal, title="Start Dragonfest"):
    minutes = discord.ui.TextInput(label="Duration (minutes)", placeholder="e.g. 30")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'dragonfest', [self.minutes.value])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class SpawnRaidModal(discord.ui.Modal, title="Spawn Raid Boss"):
    hours = discord.ui.TextInput(label="Duration (hours, 1-24)", placeholder="e.g. 4", required=False)

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            args = [self.hours.value] if self.hours.value.strip() else []
            await _run(interaction, self.bot, 'spawnraid', args)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class SetNestLevelModal(discord.ui.Modal, title="Set Dragon Nest Level"):
    user_id = discord.ui.TextInput(label="User ID", placeholder="123456789012345678")
    level   = discord.ui.TextInput(label="Level (0-20)", placeholder="e.g. 10")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(self.user_id.value))
            await _run(interaction, self.bot, 'set-dragonnest-level',
                       [self.level.value], mentions=[user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class FixSoftlockModal(discord.ui.Modal, title="Fix Softlock"):
    user_id = discord.ui.TextInput(label="User ID", placeholder="123456789012345678")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(self.user_id.value))
            await _run(interaction, self.bot, 'fix-softlock', [], mentions=[user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class SetStatusModal(discord.ui.Modal, title="Set Bot Status"):
    activity_text = discord.ui.TextInput(
        label="Activity Text",
        placeholder="e.g. Dragon Bot",
        required=False,
    )

    def __init__(self, bot, status_value: discord.Status, activity_type):
        super().__init__()
        self.bot = bot
        self.status_value = status_value
        self.activity_type = activity_type

    async def on_submit(self, interaction: discord.Interaction):
        text = self.activity_text.value.strip()
        if self.activity_type is None or not text:
            activity = None
        else:
            activity = discord.Activity(type=self.activity_type, name=text)
        await self.bot.change_presence(status=self.status_value, activity=activity)
        await interaction.response.send_message("✅ Status updated!", ephemeral=True)


# ── Give Sub-Views ─────────────────────────────────────────────────────────────

def _give_embed(title: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, color=color)


class GiveCoinsView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.send_modal(GiveCoinsAmountModal(self.bot, select.values[0]))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎁 Give", discord.Color.green()), view=GiveView(self.bot))


class GiveDragonsView(discord.ui.View):
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
            await interaction.response.send_message(
                "❌ Select a user and dragon type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GiveDragonsAmountModal(self.bot, self.selected_user, self.selected_dragon))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎁 Give", discord.Color.green()), view=GiveView(self.bot))


class GivePackView(discord.ui.View):
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
            await interaction.response.send_message(
                "❌ Select a user and pack type first.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GivePackAmountModal(self.bot, self.guild_id, self.selected_user, self.selected_pack))

    @discord.ui.button(label="Change Guild", emoji="🏠", style=discord.ButtonStyle.secondary, row=2)
    async def change_guild(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(_ChangeGuildModal(self))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎁 Give", discord.Color.green()), view=GiveView(self.bot))


class GiveDragonscaleView(discord.ui.View):
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
            await interaction.response.send_message(
                "❌ Select a user and duration first.", ephemeral=True)
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

    @discord.ui.button(label="Change Guild", emoji="🏠", style=discord.ButtonStyle.secondary, row=2)
    async def change_guild(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(_ChangeGuildModal(self))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=3)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎁 Give", discord.Color.green()), view=GiveView(self.bot))


class GrantPassView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select user…", row=0)
    async def user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.send_modal(GrantPassLevelsModal(self.bot, select.values[0]))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎁 Give", discord.Color.green()), view=GiveView(self.bot))


# ── Category Views ─────────────────────────────────────────────────────────────

class GiveView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot

    @discord.ui.button(label="Give Coins", emoji="🪙", style=discord.ButtonStyle.primary)
    async def give_coins(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🪙 Give Coins", discord.Color.gold()),
            view=GiveCoinsView(self.bot))

    @discord.ui.button(label="Give Dragons", emoji="🐉", style=discord.ButtonStyle.primary)
    async def give_dragons(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🐉 Give Dragons", discord.Color.green()),
            view=GiveDragonsView(self.bot))

    @discord.ui.button(label="Give Pack", emoji="📦", style=discord.ButtonStyle.primary)
    async def give_pack(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("📦 Give Pack", discord.Color.blue()),
            view=GivePackView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Give Dragonscale", emoji="🟪", style=discord.ButtonStyle.primary)
    async def give_dragonscale(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🟪 Give Dragonscale", discord.Color.purple()),
            view=GiveDragonscaleView(self.bot, interaction.guild_id))

    @discord.ui.button(label="Grant Pass Level", emoji="🎫", style=discord.ButtonStyle.secondary)
    async def pass_grant(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(
            embed=_give_embed("🎫 Grant Dragonpass Level", discord.Color.purple()),
            view=GrantPassView(self.bot))

    @discord.ui.button(label="Giveaway", emoji="🎁", style=discord.ButtonStyle.secondary)
    async def giveaway(self, interaction: discord.Interaction, _):
        await interaction.response.defer(ephemeral=True)
        await _run(interaction, self.bot, 'giveaway', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


class ResetView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=120); self.bot = bot

    @discord.ui.button(label="Reset Perks", emoji="🔄", style=discord.ButtonStyle.danger)
    async def reset_perks(self, i, _):
        await i.response.send_modal(ResetUserModal(self.bot, 'reset-perks', 'Reset Dragon Nest Perks'))

    @discord.ui.button(label="Reset Inventory", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def reset_inventory(self, i, _):
        await i.response.send_modal(ResetUserModal(self.bot, 'resetinventory', 'Reset Inventory'))

    @discord.ui.button(label="Reset Breeding", emoji="🥚", style=discord.ButtonStyle.danger)
    async def reset_breeding(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'resetbreeding', [])

    @discord.ui.button(label="Reset Breed CD", emoji="⏱️", style=discord.ButtonStyle.secondary)
    async def reset_breed_cd(self, i, _):
        await i.response.send_modal(ResetUserModal(self.bot, 'resetbreedcooldown', 'Reset Breed Cooldown'))

    @discord.ui.button(label="Reset Quests", emoji="📋", style=discord.ButtonStyle.danger)
    async def reset_quests(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'resetquests', [])

    @discord.ui.button(label="Reset Battlepass", emoji="🎫", style=discord.ButtonStyle.danger)
    async def reset_battlepass(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'resetbattlepass', [])

    @discord.ui.button(label="Reset Bingo", emoji="🎯", style=discord.ButtonStyle.danger, row=1)
    async def reset_bingo(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'resetbingo', [])

    @discord.ui.button(label="Reset Spawn", emoji="🌀", style=discord.ButtonStyle.secondary, row=1)
    async def reset_spawn(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'resetspawn', [])

    @discord.ui.button(label="Reset Adventure CD", emoji="🗺️", style=discord.ButtonStyle.secondary, row=1)
    async def reset_adventure_cd(self, i, _):
        await i.response.send_modal(ResetUserModal(self.bot, 'resetadventurecd', 'Reset Adventure Cooldowns'))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, i, _):
        await i.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


class SpawnView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=120); self.bot = bot

    @discord.ui.button(label="Spawn Raid Boss", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def spawn_raid(self, i, _): await i.response.send_modal(SpawnRaidModal(self.bot))

    @discord.ui.button(label="Spawn Black Market", emoji="🏴‍☠️", style=discord.ButtonStyle.primary)
    async def spawn_bm(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'spawnblackmarket', [])

    @discord.ui.button(label="Dragonfest", emoji="🎉", style=discord.ButtonStyle.primary)
    async def dragonfest(self, i, _): await i.response.send_modal(DragonFestModal(self.bot))

    @discord.ui.button(label="Kill Raid Boss", emoji="💀", style=discord.ButtonStyle.danger)
    async def kill_raid(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'raidkill', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, i, _):
        await i.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


class InfoView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=120); self.bot = bot

    @discord.ui.button(label="Spawn Status", emoji="🔍", style=discord.ButtonStyle.secondary)
    async def spawn_status(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'spawnstatus', [])

    @discord.ui.button(label="DB Status", emoji="🗄️", style=discord.ButtonStyle.secondary)
    async def db_status(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'dbstatus', [])

    @discord.ui.button(label="Raid Info", emoji="⚔️", style=discord.ButtonStyle.secondary)
    async def raid_info(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'raidinfo', [])

    @discord.ui.button(label="List Softlocks", emoji="🔒", style=discord.ButtonStyle.secondary)
    async def list_softlock(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'list-softlock', [])

    @discord.ui.button(label="Fix Softlock", emoji="🔓", style=discord.ButtonStyle.primary)
    async def fix_softlock(self, i, _): await i.response.send_modal(FixSoftlockModal(self.bot))

    @discord.ui.button(label="Set Nest Level", emoji="🏰", style=discord.ButtonStyle.primary)
    async def set_nest(self, i, _): await i.response.send_modal(SetNestLevelModal(self.bot))

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, i, _):
        await i.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


class DangerView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=120); self.bot = bot

    @discord.ui.button(label="Clear Events", emoji="🧹", style=discord.ButtonStyle.danger)
    async def clear_events(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'clearevents', [])

    @discord.ui.button(label="Wipe Server", emoji="💣", style=discord.ButtonStyle.danger)
    async def wipe_server(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'wipeserver', [])

    @discord.ui.button(label="Restart Bot", emoji="🔁", style=discord.ButtonStyle.danger)
    async def restart(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'restart', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=1)
    async def back(self, i, _):
        await i.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


_STATUS_VALUE_MAP = {
    "online":    discord.Status.online,
    "idle":      discord.Status.idle,
    "dnd":       discord.Status.dnd,
    "invisible": discord.Status.invisible,
}
_ACTIVITY_VALUE_MAP = {
    "none":      None,
    "playing":   discord.ActivityType.playing,
    "watching":  discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "streaming": discord.ActivityType.streaming,
}


class StatusView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot
        self.selected_status = discord.Status.online
        self.selected_activity = None

    @discord.ui.select(
        placeholder="Status…",
        options=_STATUS_OPTIONS,
        row=0,
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_status = _STATUS_VALUE_MAP[select.values[0]]
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Activity type…",
        options=_ACTIVITY_OPTIONS,
        row=1,
    )
    async def activity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_activity = _ACTIVITY_VALUE_MAP[select.values[0]]
        await interaction.response.defer()

    @discord.ui.button(label="Set Status", emoji="🤖", style=discord.ButtonStyle.primary, row=2)
    async def set_status(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            SetStatusModal(self.bot, self.selected_status, self.selected_activity)
        )

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


# ── Main Panel ────────────────────────────────────────────────────────────────

def _main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🛠️ Dev Panel",
        description="Select a category below.",
        color=discord.Color.from_rgb(88, 101, 242),
    )
    embed.add_field(name="🎁 Give",    value="Coins, dragons, packs, premium, giveaway", inline=False)
    embed.add_field(name="🔄 Reset",   value="Perks, inventory, battlepass, bingo, breeding, quests", inline=False)
    embed.add_field(name="⚔️ Spawn",   value="Raid boss, black market, dragonfest, raid kill", inline=False)
    embed.add_field(name="📊 Info",    value="Spawn status, DB status, raid info, softlocks, nest level", inline=False)
    embed.add_field(name="⚠️ Danger",  value="Clear events, wipe server, restart", inline=False)
    embed.add_field(name="🤖 Status",  value="Online/idle/dnd/invisible, activity text", inline=False)
    return embed


class DevPanelView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=180); self.bot = bot

    @discord.ui.button(label="🎁 Give",   style=discord.ButtonStyle.primary)
    async def give(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="🎁 Give", color=discord.Color.green()),
            view=GiveView(self.bot))

    @discord.ui.button(label="🔄 Reset",  style=discord.ButtonStyle.danger)
    async def reset(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="🔄 Reset", color=discord.Color.orange()),
            view=ResetView(self.bot))

    @discord.ui.button(label="⚔️ Spawn",  style=discord.ButtonStyle.primary)
    async def spawn(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="⚔️ Spawn", color=discord.Color.red()),
            view=SpawnView(self.bot))

    @discord.ui.button(label="📊 Info",   style=discord.ButtonStyle.secondary)
    async def info(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="📊 Info", color=discord.Color.blue()),
            view=InfoView(self.bot))

    @discord.ui.button(label="⚠️ Danger", style=discord.ButtonStyle.danger, row=1)
    async def danger(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="⚠️ Danger Zone", color=discord.Color.dark_red()),
            view=DangerView(self.bot))

    @discord.ui.button(label="🤖 Status", style=discord.ButtonStyle.secondary, row=1)
    async def status(self, i, _):
        await i.response.edit_message(
            embed=discord.Embed(title="🤖 Bot Status", color=discord.Color.blurple()),
            view=StatusView(self.bot))


# ── Cog ────────────────────────────────────────────────────────────────────────

class DevPanelCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="devpanel", description="Dev control panel")
    async def devpanel(self, interaction: discord.Interaction):
        if interaction.user.id != DEV_USER_ID:
            await interaction.response.send_message("❌ Access denied.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_main_embed(), view=DevPanelView(self.bot), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(DevPanelCog(bot))
