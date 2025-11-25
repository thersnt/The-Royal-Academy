import discord
from discord.ext import commands
import sqlite3
import os
import json
# 💡 นำเข้า load_data, save_data และ PROFILE_FILE เพื่อจัดการไฟล์ JSON
from utils import load_data, save_data, PROFILE_FILE

DB_NAME = 'school_data.db'

class DataCleanup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """ทำงานเมื่อสมาชิกออกจากเซิร์ฟเวอร์: ลบข้อมูลทุกอย่าง"""
        user_id = member.id
        print(f"👋 Member {member.name} (ID: {user_id}) has left. Starting data cleanup...")

        # 1. ลบข้อมูลจากฐานข้อมูล SQLite (เงิน, ไอเทม, ประวัติ)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 💰 ลบกระเป๋าเงิน (Economy)
                cursor.execute("DELETE FROM royals WHERE user_id = ?", (user_id,))
                
                # 📜 ลบประวัติธุรกรรมที่เกี่ยวข้อง (Transactions)
                # ลบทั้งที่เป็นผู้โอน (Source) และผู้รับ (Target) เพื่อความสะอาดหมดจด
                cursor.execute("DELETE FROM transactions WHERE source_id = ? OR target_id = ?", (user_id, user_id))
                
                # 🎒 ลบไอเทมในกระเป๋า (Inventory)
                cursor.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
                
                # 🛍️ ลบประวัติการซื้อของ (Sales History)
                cursor.execute("DELETE FROM sales_history WHERE user_id = ?", (user_id,))
                
                # 🎭 ลบข้อมูล RP Reward (RP System)
                # (ถ้าตารางนี้มีอยู่ จากโค้ด rp_system.py)
                cursor.execute("DELETE FROM rp_rewards WHERE user_id = ?", (user_id,))
                
                conn.commit()
                print(f"✅ [Database] Deleted records for {member.name}")
                
        except Exception as e:
            print(f"❌ [Database] Error cleaning up for {member.name}: {e}")

        # 2. ลบข้อมูลโปรไฟล์ JSON (Profiles)
        try:
            profiles = load_data(PROFILE_FILE)
            if str(user_id) in profiles:
                del profiles[str(user_id)]
                save_data(PROFILE_FILE, profiles)
                print(f"✅ [Profile] Deleted JSON profile for {member.name}")
            else:
                print(f"ℹ️ [Profile] No JSON profile found for {member.name}")
                
        except Exception as e:
            print(f"❌ [Profile] Error cleaning JSON for {member.name}: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(DataCleanup(bot))