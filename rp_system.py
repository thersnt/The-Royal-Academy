import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
import datetime
import typing
import re 
from utils import load_data, PROFILE_FILE 

# --- ⚙️ RP SYSTEM CONFIGURATION ---
DB_NAME = 'school_data.db' 
CURRENCY_SYMBOL = "R"
RP_COOLDOWN_SECONDS = 60      
RP_MIN_LENGTH = 250 # [UPDATED] เปลี่ยนกลับมานับตัวอักษร (250 ตัว)

# รายชื่อยศที่สามารถดูสถิติของคนอื่นได้
STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"]

RP_CHANNEL_REWARDS = {
    # --- Zone A (ห้องทั่วไป ได้ 1 R) ---
    1441113703062835291: 1,
    1441115575433560175: 1,
    1441374152207503512: 1,
    1441374748679606304: 1,
    1441375527125651517: 1,
    1441376440154325002: 1,
    1441377029357310052: 1,
    1441377304558440519: 1,
    1441378241461092354: 1,
    1441378540577620091: 1,
    1441378726981009438: 1,
    1441379394634387547: 1,
    1441380169762738257: 1,
    1441380305276633088: 1,
    1441380460596039831: 1,
    1441380760576856076: 1,
    1441380993612386324: 1,
    1441381134037549206: 1,
    1441381292561137724: 1,
}

LAST_RP_POST = {} 

class RPSystem(commands.Cog):
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
            CREATE TABLE IF NOT EXISTS rp_rewards (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                amount INTEGER,
                timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    async def _notify_wallet_thread(self, target_member: discord.Member, amount: int, new_balance: int, is_revoke: bool = False):
        if is_revoke:
            title = "💸 RP Reward ถูกเรียกคืน!"
            description = (
                f"เนื่องจากโพสต์ RP ของคุณถูกลบ ระบบจึงทำการหักคืน **{amount:,} {CURRENCY_SYMBOL}**\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
            color = discord.Color.red()
        else:
            title = "🎁 RP Bonus เข้าบัญชี!"
            description = (
                f"คุณได้รับโบนัส RP **{amount:,} {CURRENCY_SYMBOL}** เข้าบัญชีจากการโรลเพลย์\n"
                f"ยอดเงินคงเหลือตอนนี้: `{new_balance:,}` {CURRENCY_SYMBOL} 🪙"
            )
            color = discord.Color.blue()

        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        embed.set_footer(text="แจ้งเตือนจากระบบ RP System")

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
                        sent_to_thread = True
                    except Exception as e:
                        print(f"Failed to send RP notification to Wallet Thread: {e}")
        except Exception as e:
            print(f"Error checking profile/thread: {e}")

        if not sent_to_thread:
            try: await target_member.send(embed=embed)
            except: pass

    # --- 📊 Command: ดูสถิติส่วนตัว (Staff ดูคนอื่นได้) ---
    @app_commands.command(name="roleplay_stats", description="ดูสถิติการโรลเพลย์ (Staff สามารถดูของคนอื่นได้)")
    @app_commands.describe(member="สมาชิกที่ต้องการดูสถิติ (สำหรับ Staff เท่านั้น)")
    async def roleplay_stats(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        
        if member and member.id != interaction.user.id:
            user_roles = [r.name for r in interaction.user.roles]
            if not any(r in STAFF_ACCESS_ROLES for r in user_roles):
                return await interaction.response.send_message(
                    "❌ สมาชิกทั่วไปสามารถดูได้เฉพาะสถิติของตัวเองเท่านั้นค่ะ", 
                    ephemeral=True
                )

        conn = self._get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM rp_rewards WHERE user_id = ?", (target.id,))
            count_res = cursor.fetchone()
            total_posts = count_res[0] if count_res else 0
            
            cursor.execute("SELECT SUM(amount) FROM rp_rewards WHERE user_id = ?", (target.id,))
            sum_res = cursor.fetchone()
            total_earnings = sum_res[0] if sum_res and sum_res[0] else 0
            
            cursor.execute("SELECT timestamp FROM rp_rewards WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (target.id,))
            time_res = cursor.fetchone()
            last_active = "ยังไม่เคยโรลเพลย์"
            if time_res:
                dt = datetime.datetime.fromisoformat(time_res[0])
                last_active = f"<t:{int(dt.timestamp())}:R> ({dt.strftime('%d/%m/%Y')})"

            embed = discord.Embed(title=f"🎭 Roleplay Statistics", color=target.color)
            embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
            embed.set_thumbnail(url=target.display_avatar.url)
            
            embed.add_field(name="📝 จำนวนโพสต์ทั้งหมด", value=f"**{total_posts:,}** ครั้ง", inline=True)
            embed.add_field(name=f"💰 รายได้รวมจาก RP", value=f"**{total_earnings:,}** {CURRENCY_SYMBOL}", inline=True)
            embed.add_field(name="🕒 เคลื่อนไหวล่าสุด", value=last_active, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error fetching stats: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการดึงข้อมูล", ephemeral=True)
        finally:
            conn.close()

    # --- 🏆 Command: Leaderboard (ดูอันดับสูงสุด) ---
    @app_commands.command(name="rp_leaderboard", description="ดู 10 อันดับผู้ที่มีการโรลเพลย์สูงสุด")
    async def rp_leaderboard(self, interaction: discord.Interaction):
        conn = self._get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT user_id, COUNT(*) as post_count, SUM(amount) as total_earned 
                FROM rp_rewards 
                GROUP BY user_id 
                ORDER BY post_count DESC 
                LIMIT 10
            """)
            data = cursor.fetchall()
            
            if not data:
                return await interaction.response.send_message("📭 ยังไม่มีข้อมูลการโรลเพลย์ในระบบ", ephemeral=True)

            embed = discord.Embed(title="🏆 Roleplay Leaderboard (Top 10)", color=discord.Color.gold())
            description = ""
            
            for index, (user_id, count, earned) in enumerate(data, start=1):
                member = interaction.guild.get_member(user_id)
                name = member.display_name if member else f"Unknown User ({user_id})"
                medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"#{index}"
                description += f"{medal} **{name}**\n"
                description += f"└ 📝 **{count:,}** โพสต์ | 💰 **{earned:,}** {CURRENCY_SYMBOL}\n"
            
            embed.description = description
            embed.set_footer(text="จัดอันดับตามจำนวนโพสต์ที่ได้รับรางวัล")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Leaderboard Error: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
        finally:
            conn.close()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        channel_id_to_check = message.channel.id
        if isinstance(message.channel, discord.Thread): channel_id_to_check = message.channel.parent_id
        
        reward_amount = RP_CHANNEL_REWARDS.get(channel_id_to_check)
        if not reward_amount: return 
             
        user_id = message.author.id
        current_time = datetime.datetime.now().timestamp()
        last_post_time = LAST_RP_POST.get(user_id, 0)
        if current_time - last_post_time < RP_COOLDOWN_SECONDS: return 

        # [UPDATED] ใช้การนับจำนวนตัวอักษร (Length) แทนการนับคำ
        if len(message.content) < RP_MIN_LENGTH: return 

        conn = self._get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO royals (user_id, balance) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?", (user_id, reward_amount, reward_amount))
            cursor.execute("INSERT INTO rp_rewards (message_id, user_id, amount, timestamp) VALUES (?, ?, ?, ?)", (message.id, user_id, reward_amount, datetime.datetime.now().isoformat()))
            conn.commit()
            
            cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (user_id,))
            new_balance = cursor.fetchone()[0]
            LAST_RP_POST[user_id] = current_time
            
            await self._notify_wallet_thread(message.author, reward_amount, new_balance, is_revoke=False)
            print(f"RP REWARD: {message.author.display_name} received {reward_amount} R (Length: {len(message.content)})")
        except Exception as e: print(f"Error processing RP reward: {e}")
        finally: conn.close()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        conn = self._get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT user_id, amount FROM rp_rewards WHERE message_id = ?", (payload.message_id,))
            data = cursor.fetchone()
            if data:
                user_id, amount = data
                cursor.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                cursor.execute("DELETE FROM rp_rewards WHERE message_id = ?", (payload.message_id,))
                conn.commit()
                
                cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (user_id,))
                new_balance = cursor.fetchone()[0]
                
                if payload.guild_id:
                    guild = self.bot.get_guild(payload.guild_id)
                    if guild:
                        member = guild.get_member(user_id)
                        if member: await self._notify_wallet_thread(member, amount, new_balance, is_revoke=True)
        except Exception as e: print(f"Error revoking RP reward: {e}")
        finally: conn.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(RPSystem(bot))