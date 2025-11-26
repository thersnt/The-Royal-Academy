import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import datetime
import os
from utils import load_data, PROFILE_FILE 

CURRENCY_SYMBOL = "R"
DB_NAME = 'school_data.db' 
STAFF_ROLE_GRANT_ACCESS = ["Empress of TRA", "Vault Keeper"]
STAFF_ROLE_SUPREME_ACCESS = "Empress of TRA" 

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME) 

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS royals (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,          
                    source_id INTEGER NOT NULL,  
                    target_id INTEGER NOT NULL,  
                    amount INTEGER NOT NULL
                )
            """)
            await db.commit()

    async def _record_transaction(self, tx_type, sid, tid, amt):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO transactions (timestamp, type, source_id, target_id, amount) VALUES (?,?,?,?,?)", 
                             (datetime.datetime.now().isoformat(), tx_type, sid, tid, amt))
            await db.commit()

    async def _notify(self, member, title, desc, color):
        embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.datetime.now())
        sent = False
        try:
            p = load_data(PROFILE_FILE)
            wid = p.get(str(member.id), {}).get('wallet_thread_id')
            if wid:
                ch = self.bot.get_channel(int(wid))
                if ch: await ch.send(embed=embed); sent = True
        except: pass
        
        if not sent:
            try: await member.send(embed=embed)
            except: pass

    @app_commands.command(name="balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        is_admin = any(r.name == STAFF_ROLE_SUPREME_ACCESS for r in interaction.user.roles)
        if member and not is_admin: return await interaction.response.send_message("❌ ไม่มีสิทธิ์ดูของคนอื่น", ephemeral=True)
        target = member or interaction.user
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (target.id,)) as c:
                res = await c.fetchone()
                bal = res[0] if res else 0
        
        await interaction.response.send_message(embed=discord.Embed(description=f"💰 ยอดเงินของ **{target.display_name}**: `{bal:,} {CURRENCY_SYMBOL}`", color=discord.Color.gold()), ephemeral=True)

    @app_commands.command(name="grant_royals")
    async def grant(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not any(r.name in STAFF_ROLE_GRANT_ACCESS for r in interaction.user.roles): return await interaction.followup.send("❌ ไม่มีสิทธิ์", ephemeral=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+?", (member.id, amount, amount))
            await db.commit()
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (member.id,)) as c: new_bal = (await c.fetchone())[0]

        await self._record_transaction('GRANT', interaction.user.id, member.id, amount)
        await self._notify(member, "✨ ได้รับ Royal Grant", f"Admin มอบ **{amount:,} R**\nคงเหลือ: `{new_bal:,} R`", discord.Color.green())
        await interaction.followup.send(f"✅ มอบ {amount} R ให้ {member.mention} แล้ว", ephemeral=False)

    @app_commands.command(name="transfer")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if amount <= 0 or interaction.user.id == member.id: return await interaction.followup.send("❌ ทำรายการไม่ได้", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (interaction.user.id,)) as c:
                res = await c.fetchone()
                bal = res[0] if res else 0
            
            if bal < amount: return await interaction.followup.send("❌ เงินไม่พอ", ephemeral=True)
            
            await db.execute("UPDATE royals SET balance=balance-? WHERE user_id=?", (amount, interaction.user.id))
            await db.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+?", (member.id, amount, amount))
            await db.commit()
            
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (interaction.user.id,)) as c: new_sender = (await c.fetchone())[0]
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (member.id,)) as c: new_rec = (await c.fetchone())[0]

        await self._record_transaction('TRANSFER', interaction.user.id, member.id, amount)
        await self._notify(member, "💸 ได้รับโอนเงิน", f"ได้รับ **{amount:,} R** จาก {interaction.user.display_name}\nคงเหลือ: `{new_rec:,} R`", discord.Color.gold())
        await interaction.followup.send(f"💸 โอน {amount} R ให้ {member.mention} แล้ว\nคงเหลือ: `{new_sender:,} R`", ephemeral=True)

    @app_commands.command(name="take_royals")
    async def take(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not any(r.name in STAFF_ROLE_GRANT_ACCESS for r in interaction.user.roles): return await interaction.followup.send("❌ ไม่มีสิทธิ์", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (member.id,)) as c:
                res = await c.fetchone()
                if not res or res[0] < amount: return await interaction.followup.send("❌ เงินเป้าหมายไม่พอให้หัก", ephemeral=True)
            
            await db.execute("UPDATE royals SET balance=balance-? WHERE user_id=?", (amount, member.id))
            await db.commit()
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (member.id,)) as c: new_bal = (await c.fetchone())[0]

        await self._record_transaction('TAKE', interaction.user.id, member.id, amount)
        await self._notify(member, "🚨 เงินถูกหัก", f"ถูกหัก **{amount:,} R**\nคงเหลือ: `{new_bal:,} R`", discord.Color.red())
        await interaction.followup.send(f"✅ หักเงิน {member.mention} เรียบร้อย", ephemeral=False)

    @app_commands.command(name="wipe_royals")
    async def wipe(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if not any(r.name == STAFF_ROLE_SUPREME_ACCESS for r in interaction.user.roles): return await interaction.followup.send("❌ ไม่มีสิทธิ์", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE royals SET balance=0 WHERE user_id=?", (member.id,))
            await db.commit()
        
        await self._record_transaction('WIPE', interaction.user.id, member.id, 0)
        await self._notify(member, "💥 บัญชีถูกรีเซ็ต", "ยอดเงินของคุณถูกรีเซ็ตเป็น 0", discord.Color.dark_red())
        await interaction.followup.send(f"✅ รีเซ็ตบัญชี {member.mention} แล้ว", ephemeral=False)

async def setup(bot):
    await bot.add_cog(Economy(bot))
