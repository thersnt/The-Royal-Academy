import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
import datetime
from utils import load_data, PROFILE_FILE 

DB_NAME = 'school_data.db' 
CURRENCY_SYMBOL = "R"
RP_COOLDOWN_SECONDS = 60      
RP_MIN_LENGTH = 250
STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"]

RP_CHANNEL_REWARDS = {
    # ใส่ Channel ID ตรงนี้
    1441113703062835291: 1,
}

LAST_RP_POST = {} 

class RPSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS rp_rewards (message_id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, timestamp TEXT)")
            await db.commit()

    async def _notify(self, user, embed, is_revoke=False):
        if is_revoke:
            embed.title = "💸 RP Revoked"
            embed.color = discord.Color.red()
        else:
            embed.title = "🎁 RP Reward"
            embed.color = discord.Color.blue()

        try:
            p = load_data(PROFILE_FILE)
            wid = p.get(str(user.id), {}).get('wallet_thread_id')
            if wid:
                ch = self.bot.get_channel(int(wid))
                if ch: await ch.send(embed=embed)
        except: pass

    @app_commands.command(name="roleplay_stats")
    async def rp_stats(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        if member and member.id != interaction.user.id:
             if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
                 return await interaction.response.send_message("❌ ไม่มีสิทธิ์ดูของคนอื่น", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*), SUM(amount) FROM rp_rewards WHERE user_id = ?", (target.id,)) as cursor:
                res = await cursor.fetchone()
                count, earned = res if res else (0, 0)
                earned = earned or 0
        
        embed = discord.Embed(title=f"🎭 RP Stats: {target.display_name}", color=target.color)
        embed.add_field(name="Posts", value=f"{count}")
        embed.add_field(name="Earned", value=f"{earned} R")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rp_leaderboard")
    async def leaderboard(self, interaction):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, COUNT(*), SUM(amount) FROM rp_rewards GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 10") as c:
                data = await c.fetchall()
        
        txt = ""
        for idx, (uid, cnt, amt) in enumerate(data, 1):
            mem = interaction.guild.get_member(uid)
            name = mem.display_name if mem else f"User {uid}"
            txt += f"{idx}. **{name}** - {cnt} posts ({amt} R)\n"
            
        await interaction.response.send_message(embed=discord.Embed(title="🏆 RP Leaderboard", description=txt, color=discord.Color.gold()))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        
        cid = message.channel.parent_id if isinstance(message.channel, discord.Thread) else message.channel.id
        reward = RP_CHANNEL_REWARDS.get(cid)
        if not reward: return

        now = datetime.datetime.now().timestamp()
        if now - LAST_RP_POST.get(message.author.id, 0) < RP_COOLDOWN_SECONDS: return
        if len(message.content) < RP_MIN_LENGTH: return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (message.author.id, reward, reward))
            await db.execute("INSERT INTO rp_rewards (message_id, user_id, amount, timestamp) VALUES (?, ?, ?, ?)", (message.id, message.author.id, reward, datetime.datetime.now().isoformat()))
            await db.commit()
            
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (message.author.id,)) as cursor:
                bal = (await cursor.fetchone())[0]
        
        LAST_RP_POST[message.author.id] = now
        
        embed = discord.Embed(description=f"ได้รับ **{reward} R**\nคงเหลือ: `{bal} R`")
        await self._notify(message.author, embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, amount FROM rp_rewards WHERE message_id = ?", (payload.message_id,)) as c:
                data = await c.fetchone()
            
            if data:
                uid, amt = data
                await db.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amt, uid))
                await db.execute("DELETE FROM rp_rewards WHERE message_id = ?", (payload.message_id,))
                await db.commit()
                
                async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (uid,)) as cursor:
                    bal = (await cursor.fetchone())[0]
                
                guild = self.bot.get_guild(payload.guild_id)
                if guild:
                    member = guild.get_member(uid)
                    if member:
                        embed = discord.Embed(description=f"หักคืน **-{amt} R** (ลบโพสต์)\nคงเหลือ: `{bal} R`")
                        await self._notify(member, embed, is_revoke=True)

async def setup(bot):
    await bot.add_cog(RPSystem(bot))
