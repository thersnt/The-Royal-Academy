import aiosqlite
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import os
from utils import load_data, PROFILE_FILE 

CURRENCY_SYMBOL = "R"
DB_NAME = 'school_data.db' 
STAFF_ROLE_GRANT_ACCESS = ["Empress of TRA", "Vault Keeper"]
STAFF_ROLE_SUPREME_ACCESS = "Empress of TRA" 

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME) 

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS royals (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            """)
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

    async def _record_transaction(self, tx_type: str, source_id: int, target_id: int, amount: int):
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO transactions (timestamp, type, source_id, target_id, amount)
                VALUES (?, ?, ?, ?, ?)
            """, (timestamp, tx_type, source_id, target_id, amount))
            await db.commit()

    def _create_base_embed(self, title_text: str, color: discord.Color = discord.Color.from_rgb(255, 192, 203)):
        embed = discord.Embed(description=title_text, color=color)
        embed.set_author(name="The Royal Academy", icon_url=self.bot.user.display_avatar.url)
        return embed

    async def _notify_recipient(self, target_member: discord.Member, source_name: str, amount: int, transaction_type: str, new_balance: int):
        if transaction_type == 'GRANT':
            title, color = "✨ คุณได้รับ Royal Grant เข้าบัญชี!", discord.Color.green()
            desc = f"Admin **{source_name}** ได้มอบ **{amount:,} {CURRENCY_SYMBOL}** ให้คุณค่ะ!\nยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
        elif transaction_type == 'TRANSFER':
            title, color = "💸 คุณได้รับโอน Royals เข้าบัญชี", discord.Color.gold()
            desc = f"คุณได้รับโอน **{amount:,} {CURRENCY_SYMBOL}** จาก **{source_name}**\nยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
        elif transaction_type == 'TAKE':
            title, color = "🚨 ยอด Royals ของคุณถูกหัก!", discord.Color.red()
            desc = f"Admin **{source_name}** ได้ทำการหัก **{amount:,} {CURRENCY_SYMBOL}** ออกจากบัญชีของคุณค่ะ\nยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
        elif transaction_type == 'WIPE':
            title, color = "💥 บัญชี Royals ถูกรีเซ็ต!", discord.Color.dark_red()
            desc = f"Admin **{source_name}** ได้รีเซ็ตยอด Royals ของคุณเป็น **0** แล้วค่ะ\nยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
        else:
            return

        embed = discord.Embed(title=title, description=desc, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_footer(text="แจ้งเตือนจากระบบ Royals Economy")

        sent_to_thread = False
        try:
            profiles = load_data(PROFILE_FILE)
            wallet_thread_id = profiles.get(str(target_member.id), {}).get('wallet_thread_id')
            if wallet_thread_id:
                wallet_thread = self.bot.get_channel(int(wallet_thread_id))
                if wallet_thread:
                    try:
                        await wallet_thread.send(embed=embed)
                        sent_to_thread = True
                    except: pass
        except: pass

        if not sent_to_thread:
            try: await target_member.send(embed=embed)
            except: pass

    @app_commands.command(name="balance", description="ตรวจสอบยอดเงิน Royals คงเหลือของคุณ")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        is_supreme = discord.utils.get(interaction.user.roles, name=STAFF_ROLE_SUPREME_ACCESS) is not None
        if member and not is_supreme:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ดูยอดเงินของสมาชิกคนอื่น", ephemeral=True)

        target = member or interaction.user
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (target.id,)) as cursor:
                result = await cursor.fetchone()
                balance = result[0] if result else 0
        
        embed = self._create_base_embed(f"💰 ยอดเงิน Royals ของ **{target.display_name}**: `{balance:,}` {CURRENCY_SYMBOL}")
        await interaction.response.send_message(embed=embed, ephemeral=True) 

    @app_commands.command(name="grant_royals", description="[STAFF] มอบเงิน Royals")
    async def grant_royals(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not any(r.name in [r.name for r in interaction.user.roles] for r in STAFF_ROLE_GRANT_ACCESS):
            return await interaction.followup.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        if amount <= 0: return await interaction.followup.send("จำนวนเงินต้องเป็นบวกเท่านั้นค่ะ", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (member.id, amount, amount))
            await db.commit()
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,)) as cursor:
                new_balance = (await cursor.fetchone())[0]

        await self._record_transaction('GRANT', interaction.user.id, member.id, amount) 
        await self._notify_recipient(member, interaction.user.display_name, amount, 'GRANT', new_balance)
        
        embed = self._create_base_embed(f"✅ **Transaction Complete:** มอบ **`{amount:,} {CURRENCY_SYMBOL}`** ให้ {member.mention} แล้ว", color=discord.Color.green())
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="transfer", description="โอนเงิน Royals ให้ผู้เล่นอื่น")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if amount <= 0: return await interaction.followup.send("จำนวนเงินต้องเป็นบวกเท่านั้นค่ะ", ephemeral=True)
        if interaction.user.id == member.id: return await interaction.followup.send("คุณไม่สามารถโอนเงินให้ตัวเองได้", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)) as cursor:
                res = await cursor.fetchone()
                sender_balance = res[0] if res else 0

            if sender_balance < amount:
                return await interaction.followup.send(f"❌ ยอดเงินไม่พอ!", ephemeral=True)

            await db.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, interaction.user.id))
            await db.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (member.id, amount, amount))
            await db.commit()

            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)) as cursor:
                new_sender_balance = (await cursor.fetchone())[0]
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,)) as cursor:
                new_recipient_balance = (await cursor.fetchone())[0]

        await self._record_transaction('TRANSFER', interaction.user.id, member.id, amount)
        await self._notify_recipient(member, interaction.user.display_name, amount, 'TRANSFER', new_recipient_balance)
        
        embed = self._create_base_embed(f"💸 โอนสำเร็จ! **{interaction.user.display_name}** โอน `{amount:,} {CURRENCY_SYMBOL}` ให้ **{member.display_name}** แล้วค่ะ\nยอดเงินของคุณ: `{new_sender_balance:,}` {CURRENCY_SYMBOL}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="take_royals", description="[STAFF] หักเงิน Royals")
    async def take_royals(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not any(r.name in [r.name for r in interaction.user.roles] for r in STAFF_ROLE_GRANT_ACCESS):
            return await interaction.followup.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,)) as cursor:
                res = await cursor.fetchone()
                current_balance = res[0] if res else 0
            
            if current_balance < amount:
                return await interaction.followup.send(f"❌ สมาชิกคนนี้มีเงินไม่พอให้หัก", ephemeral=True)

            await db.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, member.id))
            await db.commit()
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,)) as cursor:
                new_balance = (await cursor.fetchone())[0]

        await self._record_transaction('TAKE', interaction.user.id, member.id, amount)
        await self._notify_recipient(member, interaction.user.display_name, amount, 'TAKE', new_balance)
        embed = self._create_base_embed(f"🚨 **Transaction Complete:** หักเงิน **`{amount:,} {CURRENCY_SYMBOL}`** จาก {member.mention}", color=discord.Color.red())
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="wipe_royals", description="[STAFF] รีเซ็ตเงิน Royals เป็น 0")
    async def wipe_royals(self, interaction: discord.
