"""One-time script: delete incorrect vote DMs from today, send correct Day 30 DM."""
import asyncio
import os
import time
import discord
from dotenv import load_dotenv

load_dotenv()

TARGET_USER_ID = 774679828594163802

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    try:
        user = await client.fetch_user(TARGET_USER_ID)
        dm = await user.create_dm()

        # Fetch last 20 DMs from bot
        today_start = int(time.time()) - 86400  # last 24h
        deleted = 0
        async for msg in dm.history(limit=20):
            if msg.author.id == client.user.id:
                ts = int(msg.created_at.timestamp())
                if ts > today_start and msg.embeds:
                    embed = msg.embeds[0]
                    # Delete vote DMs that show wrong day (Day 4, 5, 7)
                    if embed.description and "Day" in embed.description and "30" not in embed.description.split("Day")[1].split("/")[0]:
                        # Check it's a vote DM (has "Thanks for voting" title)
                        if "voting" in (embed.title or "").lower():
                            print(f"Deleting: {embed.description[:60]}")
                            await msg.delete()
                            deleted += 1
                            await asyncio.sleep(0.5)

        print(f"Deleted {deleted} incorrect vote DMs")

        # Send correct Day 30 DM
        embed = discord.Embed(
            title="🗳️ Thanks for voting! (Corrected)",
            color=discord.Color.gold(),
        )
        embed.description = "**Day 30/30** in your current cycle"
        embed.add_field(name="Today's Reward", value="🎁 **⭐ Dragonscale Pack + 3,000 coins**\n⭐ **30-day cycle complete! Starting over.**", inline=False)
        embed.add_field(name="🔥 Vote Streak", value="**11** votes in a row | Total: **30**", inline=False)
        embed.set_footer(text="Vote every 12h to keep your streak! (Reward was manually applied)")
        await user.send(embed=embed)
        print("Sent correct Day 30 DM")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

asyncio.run(client.start(os.getenv('DISCORD_BOT_TOKEN')))
