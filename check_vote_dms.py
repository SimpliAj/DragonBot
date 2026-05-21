"""Check vote DM count for today's voters and fix duplicates."""
import asyncio
import os
import time
import sqlite3
import discord
from dotenv import load_dotenv

load_dotenv()

# Users who voted today (excluding already-fixed DEV user)
TODAY_VOTERS = [
    1220796094942810125,
    893360722367635476,
]

TODAY_START = int(time.time()) - 86400  # last 24h

intents = discord.Intents.default()
client = discord.Client(intents=intents)

def get_db():
    conn = sqlite3.connect('dragon_bot.db')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    for user_id in TODAY_VOTERS:
        try:
            user = await client.fetch_user(user_id)
            dm = await user.create_dm()

            vote_dms = []
            async for msg in dm.history(limit=30):
                if msg.author.id == client.user.id:
                    ts = int(msg.created_at.timestamp())
                    if ts > TODAY_START and msg.embeds:
                        embed = msg.embeds[0]
                        if embed.title and "voting" in embed.title.lower():
                            vote_dms.append((msg, embed, ts))

            print(f"\nUser {user_id}: {len(vote_dms)} vote DM(s) today")
            for msg, embed, ts in vote_dms:
                print(f"  - {embed.description[:50] if embed.description else 'no desc'} @ {time.strftime('%H:%M', time.gmtime(ts))}")

            if len(vote_dms) <= 1:
                print(f"  → No duplicates, skipping")
                continue

            # Has duplicates: keep the LAST one (most recent/correct), delete others
            vote_dms.sort(key=lambda x: x[2])  # sort by timestamp ascending
            to_delete = vote_dms[:-1]  # keep last

            # Figure out correct total_votes: subtract extra votes from DB
            extra_votes = len(to_delete)
            conn = get_db()
            row = conn.execute('SELECT total_votes, current_streak FROM vote_streaks WHERE user_id = ?', (user_id,)).fetchone()
            if row:
                correct_total = row[0] - extra_votes
                print(f"  → Fixing total_votes: {row[0]} → {correct_total} (removing {extra_votes} duplicates)")
                conn.execute('UPDATE vote_streaks SET total_votes = ? WHERE user_id = ?', (correct_total, user_id))
                conn.commit()
            conn.close()

            # Delete duplicate DMs
            for msg, embed, ts in to_delete:
                print(f"  → Deleting duplicate: {embed.description[:40] if embed.description else ''}")
                await msg.delete()
                await asyncio.sleep(0.5)

            print(f"  ✓ Fixed user {user_id}")

        except Exception as e:
            print(f"Error for user {user_id}: {e}")

    print("\nDone!")
    await client.close()

asyncio.run(client.start(os.getenv('DISCORD_BOT_TOKEN')))
