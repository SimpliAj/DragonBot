"""
cogs/devpanel.py - /devpanel slash command (DEV_USER_ID only).
Replaces all -db prefix commands with an interactive panel.
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import DEV_USER_ID


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

class GiveCoinsModal(discord.ui.Modal, title="Give Coins"):
    user_id  = discord.ui.TextInput(label="User ID", placeholder="123456789012345678")
    amount   = discord.ui.TextInput(label="Amount", placeholder="e.g. 10000")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(self.user_id.value))
            await _run(interaction, self.bot, 'givecoins',
                       [self.amount.value], mentions=[user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class GiveDragonsModal(discord.ui.Modal, title="Give Dragons"):
    user_id     = discord.ui.TextInput(label="User ID", placeholder="123456789012345678")
    dragon_type = discord.ui.TextInput(label="Dragon type (or * for all)", placeholder="stone / ember / * ...")
    amount      = discord.ui.TextInput(label="Amount", placeholder="e.g. 5")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(self.user_id.value))
            await _run(interaction, self.bot, 'givedragons',
                       [self.dragon_type.value, self.amount.value], mentions=[user])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class GivePackModal(discord.ui.Modal, title="Give Pack"):
    guild_id_  = discord.ui.TextInput(label="Guild ID", placeholder="123456789012345678")
    user_id    = discord.ui.TextInput(label="User ID",  placeholder="123456789012345678")
    pack_type  = discord.ui.TextInput(label="Pack type", placeholder="wooden / stone / bronze / silver / gold / diamond")
    amount     = discord.ui.TextInput(label="Amount", placeholder="e.g. 3")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givepack',
                       [self.guild_id_.value, self.user_id.value,
                        self.pack_type.value, self.amount.value])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class GivePremiumModal(discord.ui.Modal, title="Give Premium"):
    guild_id_ = discord.ui.TextInput(label="Guild ID", placeholder="123456789012345678")
    user_id   = discord.ui.TextInput(label="User ID",  placeholder="123456789012345678")
    days      = discord.ui.TextInput(label="Days", placeholder="e.g. 30")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await _run(interaction, self.bot, 'givepremium',
                       [self.guild_id_.value, self.user_id.value, self.days.value])
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class PassGrantModal(discord.ui.Modal, title="Grant Dragonpass Level"):
    user_id = discord.ui.TextInput(label="User ID", placeholder="123456789012345678")
    levels  = discord.ui.TextInput(label="Levels to grant", placeholder="e.g. 5")

    def __init__(self, bot): super().__init__(); self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(self.user_id.value))
            await _run(interaction, self.bot, 'passgrant',
                       [self.levels.value], mentions=[user])
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


# ── Category Views ─────────────────────────────────────────────────────────────

class GiveView(discord.ui.View):
    def __init__(self, bot): super().__init__(timeout=120); self.bot = bot

    @discord.ui.button(label="Give Coins", emoji="🪙", style=discord.ButtonStyle.primary)
    async def give_coins(self, i, _): await i.response.send_modal(GiveCoinsModal(self.bot))

    @discord.ui.button(label="Give Dragons", emoji="🐉", style=discord.ButtonStyle.primary)
    async def give_dragons(self, i, _): await i.response.send_modal(GiveDragonsModal(self.bot))

    @discord.ui.button(label="Give Pack", emoji="📦", style=discord.ButtonStyle.primary)
    async def give_pack(self, i, _): await i.response.send_modal(GivePackModal(self.bot))

    @discord.ui.button(label="Give Premium", emoji="⭐", style=discord.ButtonStyle.primary)
    async def give_premium(self, i, _): await i.response.send_modal(GivePremiumModal(self.bot))

    @discord.ui.button(label="Grant Pass Level", emoji="🎫", style=discord.ButtonStyle.secondary)
    async def pass_grant(self, i, _): await i.response.send_modal(PassGrantModal(self.bot))

    @discord.ui.button(label="Giveaway", emoji="🎁", style=discord.ButtonStyle.secondary)
    async def giveaway(self, i, _):
        await i.response.defer(ephemeral=True)
        await _run(i, self.bot, 'giveaway', [])

    @discord.ui.button(label="← Back", style=discord.ButtonStyle.gray, row=2)
    async def back(self, i, _):
        await i.response.edit_message(embed=_main_embed(), view=DevPanelView(self.bot))


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
