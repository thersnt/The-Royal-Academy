import sqlite3
import datetime
import discord
from discord.ext import commands
from discord import app_commands
import os
import typing
# 💡 นำเข้า load_data และตัวแปรต่างๆ จาก utils
from utils import load_data, save_data, BALANCE_FILE, PROFILE_FILE 

# --- ⚙️ การตั้งค่าระบบเงินตรา ---
CURRENCY_NAME = "Royals"
CURRENCY_SYMBOL = "R"
DB_NAME = 'school_data.db' 

# 🚨 DEFINING NEW PRIVILEGE ROLES 🚨
STAFF_ROLE_GRANT_ACCESS = ["Empress of TRA", "Vault Keeper"]
STAFF_ROLE_SUPREME_ACCESS = "Empress of TRA" 
# ------------------------------------

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME) 
        self._create_tables()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS royals (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,          
                source_id INTEGER NOT NULL,  
                target_id INTEGER NOT NULL,  
                amount INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _record_transaction(self, tx_type: str, source_id: int, target_id: int, amount: int):
        conn = self._get_db()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        cursor.execute("""
            INSERT INTO transactions (timestamp, type, source_id, target_id, amount)
            VALUES (?, ?, ?, ?, ?)
        """, (timestamp, tx_type, source_id, target_id, amount))
        
        conn.commit()
        conn.close()

    def _create_base_embed(self, title_text: str, color: discord.Color = discord.Color.from_rgb(255, 192, 203)):
        embed = discord.Embed(
            description=title_text,
            color=color
        )
        embed.set_author(
            name="The Royal Academy",
            icon_url=self.bot.user.display_avatar.url
        )
        return embed

    def _get_display_name(self, guild: discord.Guild, user_id: int):
        member = guild.get_member(user_id)
        if member:
            return member.display_name
        user = self.bot.get_user(user_id)
        if user:
            return user.display_name
        return f"ID: {user_id}"

    # --- 🌟 Helper: Notify (Thread -> Fallback to DM) ---
    async def _notify_recipient(self, target_member: discord.Member, source_name: str, amount: int, transaction_type: str, new_balance: int):
        
        # กำหนดข้อความตามประเภทธุรกรรม
        if transaction_type == 'GRANT':
            title = "✨ คุณได้รับ Royal Grant เข้าบัญชี!"
            color = discord.Color.green()
            description = (
                f"Admin **{source_name}** ได้มอบ **{amount:,} {CURRENCY_SYMBOL}** ให้คุณค่ะ!\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
        elif transaction_type == 'TRANSFER':
            title = "💸 คุณได้รับโอน Royals เข้าบัญชี"
            color = discord.Color.gold()
            description = (
                f"คุณได้รับโอน **{amount:,} {CURRENCY_SYMBOL}** จาก **{source_name}**\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
        elif transaction_type == 'TAKE':
            title = "🚨 ยอด Royals ของคุณถูกหัก!"
            color = discord.Color.red()
            description = (
                f"Admin **{source_name}** ได้ทำการหัก **{amount:,} {CURRENCY_SYMBOL}** ออกจากบัญชีของคุณค่ะ\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
        elif transaction_type == 'WIPE':
            title = "💥 บัญชี Royals ถูกรีเซ็ต!"
            color = discord.Color.dark_red()
            description = (
                f"Admin **{source_name}** ได้รีเซ็ตยอด Royals ของคุณเป็น **0** แล้วค่ะ\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
        else:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text="แจ้งเตือนจากระบบ Royals Economy")

        # --- 🔔 LOGIC การแจ้งเตือน: Thread ก่อน ถ้าไม่ได้ค่อย DM ---
        sent_to_thread = False
        
        try:
            profiles = load_data(PROFILE_FILE)
            user_id_str = str(target_member.id)
            wallet_thread_id = profiles.get(user_id_str, {}).get('wallet_thread_id')
            
            if wallet_thread_id:
                wallet_thread = self.bot.get_channel(int(wallet_thread_id))
                if wallet_thread:
                    try:
                        await wallet_thread.send(embed=embed)
                        sent_to_thread = True # ✅ ส่งเข้าเธรดสำเร็จ
                    except Exception as e:
                        print(f"Failed to send notification to Wallet Thread {wallet_thread.name}: {e}")
        except Exception as e:
             print(f"Error checking profile/thread: {e}")

        # ถ้าส่งเข้าเธรดไม่สำเร็จ (ไม่มีเธรด หรือ Error) -> ส่ง DM
        if not sent_to_thread:
            try:
                await target_member.send(embed=embed)
                # print(f"Sent DM to {target_member.display_name}")
            except discord.Forbidden:
                print(f"WARNING: Cannot send DM to {target_member.display_name}. DMs are disabled.")
            except Exception as e:
                print(f"Error sending DM: {e}")
            
    # ------------------------------------
    # COMMANDS
    # ------------------------------------

    @app_commands.command(name="balance", description="ตรวจสอบยอดเงิน Royals คงเหลือของคุณ")
    @app_commands.describe(member="สมาชิกที่คุณต้องการตรวจสอบยอดเงิน (Empress of TRA เท่านั้น)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        is_supreme = discord.utils.get(interaction.user.roles, name=STAFF_ROLE_SUPREME_ACCESS) is not None
        
        if member and not is_supreme:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ดูยอดเงินของสมาชิกคนอื่น (ต้องเป็น Empress of TRA)", ephemeral=True)

        target = member or interaction.user
        
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (target.id,))
        result = cursor.fetchone()
        balance = result[0] if result else 0
        conn.close()
        
        embed = self._create_base_embed(f"💰 ยอดเงิน Royals ของ **{target.display_name}**: `{balance:,}` {CURRENCY_SYMBOL}")
        await interaction.response.send_message(embed=embed, ephemeral=True) 

    @app_commands.command(name="grant_royals", description="[STAFF] มอบเงิน Royals")
    async def grant_royals(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        
        member_roles = [r.name for r in interaction.user.roles]
        has_permission = any(role in member_roles for role in STAFF_ROLE_GRANT_ACCESS)
        
        if not has_permission:
            return await interaction.followup.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
            
        if amount <= 0:
            return await interaction.followup.send("จำนวนเงินต้องเป็นบวกเท่านั้นค่ะ", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
            (member.id, amount, amount)
        )
        conn.commit()
        self._record_transaction('GRANT', interaction.user.id, member.id, amount) 
        
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,))
        new_balance = cursor.fetchone()[0]
        conn.close()
        
        await self._notify_recipient(member, interaction.user.display_name, amount, 'GRANT', new_balance)
        
        embed = self._create_base_embed(
            f"✅ **Transaction Complete:** เจ้าหน้าที่ {interaction.user.mention} ได้มอบ **`{amount:,} {CURRENCY_SYMBOL}`** ให้กับ {member.mention} แล้ว\n"
            f"ยอดเงินของ {member.display_name} ตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="transfer", description="โอนเงิน Royals ให้ผู้เล่นอื่น")
    async def transfer(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)

        if amount <= 0: return await interaction.followup.send("จำนวนเงินต้องเป็นบวกเท่านั้นค่ะ", ephemeral=True)
        if interaction.user.id == member.id: return await interaction.followup.send("คุณไม่สามารถโอนเงินให้ตัวเองได้", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,))
        sender_balance_result = cursor.fetchone()
        sender_balance = sender_balance_result[0] if sender_balance_result else 0

        if sender_balance < amount:
            conn.close()
            return await interaction.followup.send(f"❌ ยอดเงินไม่พอ! คุณมี `{sender_balance:,}` Royals แต่ต้องการโอน `{amount:,}` Royals", ephemeral=True)

        cursor.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, interaction.user.id))
        cursor.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (member.id, amount, amount))
        conn.commit()
        
        self._record_transaction('TRANSFER', interaction.user.id, member.id, amount)
        
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,))
        new_sender_balance = cursor.fetchone()[0]
        
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,))
        new_recipient_balance = cursor.fetchone()[0]
        conn.close()
        
        await self._notify_recipient(member, interaction.user.display_name, amount, 'TRANSFER', new_recipient_balance)
        
        embed = self._create_base_embed(
            f"💸 โอนสำเร็จ! **{interaction.user.display_name}** โอน `{amount:,} {CURRENCY_SYMBOL}` ให้ **{member.display_name}** แล้วค่ะ\n"
            f"ยอดเงินของคุณตอนนี้: `{new_sender_balance:,}` {CURRENCY_SYMBOL} 🪙"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- 👇 ส่วนที่เพิ่มเข้ามาใหม่: TAKE และ WIPE 👇 ---

    @app_commands.command(name="take_royals", description="[STAFF] หักเงิน Royals (Empress of TRA และ Vault Keeper เท่านั้น)")
    async def take_royals(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        await interaction.response.defer(ephemeral=True)
        
        member_roles = [r.name for r in interaction.user.roles]
        has_permission = any(role in member_roles for role in STAFF_ROLE_GRANT_ACCESS)
        
        if not has_permission:
            return await interaction.followup.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
            
        if amount <= 0:
            return await interaction.followup.send("จำนวนเงินต้องเป็นบวกเท่านั้นค่ะ", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        
        # ตรวจสอบว่าผู้รับมีเงินพอให้หักไหม
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,))
        result = cursor.fetchone()
        current_balance = result[0] if result else 0
        
        if current_balance < amount:
            conn.close()
            return await interaction.followup.send(f"❌ สมาชิกคนนี้มีเงินไม่พอให้หัก (มีแค่ {current_balance:,})", ephemeral=True)

        cursor.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, member.id))
        conn.commit()
        
        self._record_transaction('TAKE', interaction.user.id, member.id, amount)
        
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,))
        new_balance = cursor.fetchone()[0]
        conn.close()
        
        # เรียกใช้ Notification
        await self._notify_recipient(member, interaction.user.display_name, amount, 'TAKE', new_balance)
        
        embed = self._create_base_embed(
            f"🚨 **Transaction Complete:** เจ้าหน้าที่ {interaction.user.mention} ได้หักเงิน **`{amount:,} {CURRENCY_SYMBOL}`** จาก {member.mention}\n"
            f"ยอดเงินของ {member.display_name} คงเหลือ: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

    @app_commands.command(name="wipe_royals", description="[STAFF] รีเซ็ตเงิน Royals เป็น 0 (Empress of TRA เท่านั้น)")
    async def wipe_royals(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        
        # WIPE สงวนสิทธิ์เฉพาะ Supreme Access หรือตามที่คุณต้องการ
        is_supreme = discord.utils.get(interaction.user.roles, name=STAFF_ROLE_SUPREME_ACCESS) is not None
        if not is_supreme:
             return await interaction.followup.send("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องเป็น Empress of TRA)", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        
        # ดึงยอดเงินเดิมเพื่อบันทึก Transaction ว่าลบไปเท่าไหร่
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (member.id,))
        result = cursor.fetchone()
        old_balance = result[0] if result else 0
        
        if old_balance == 0:
            conn.close()
            return await interaction.followup.send("❌ สมาชิกคนนี้มียอดเงินเป็น 0 อยู่แล้ว", ephemeral=True)

        cursor.execute("UPDATE royals SET balance = 0 WHERE user_id = ?", (member.id,))
        conn.commit()
        
        self._record_transaction('WIPE', interaction.user.id, member.id, old_balance)
        conn.close()
        
        # เรียกใช้ Notification (amount เป็น 0 หรือ old_balance ก็ได้ แต่ใน description เราเขียนว่า 'เป็น 0' อยู่แล้ว)
        await self._notify_recipient(member, interaction.user.display_name, old_balance, 'WIPE', 0)
        
        embed = self._create_base_embed(
            f"💥 **Account Wiped:** เจ้าหน้าที่ {interaction.user.mention} ได้รีเซ็ตยอดเงินของ {member.mention} เป็น **0** เรียบร้อยแล้ว",
            color=discord.Color.dark_red()
        )
        await interaction.followup.send(embed=embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
