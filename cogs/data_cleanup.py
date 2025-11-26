import discord
from discord.ext import commands
import aiosqlite
import os
from utils import load_data, save_data, PROFILE_FILE

DB_NAME = 'school_data.db'

class DataCleanup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        uid = member.id
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM royals WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM transactions WHERE source_id=? OR target_id=?", (uid, uid))
            await db.execute("DELETE FROM inventory WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM sales_history WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM rp_rewards WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM activity_logs WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM club_members WHERE user_id=?", (uid,))
            # Handle club owner deletion logic if needed
            await db.commit()
        
        profiles = load_data(PROFILE_FILE)
        if str(uid) in profiles:
            del profiles[str(uid)]
            await save_data(profiles, PROFILE_FILE)

async def setup(bot):
    await bot.add_cog(DataCleanup(bot))

