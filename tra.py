import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import sqlite3

# 🚨 ลบการ Import ที่เกี่ยวข้องกับ Keep Alive (Flask/Thread) ออกไป
# from threading import Thread
# from flask import Flask

# ----------------- A. ส่วนสร้าง Web Server สำหรับ Keep Alive -----------------
# 🚨 ลบโค้ด Flask Web Server ทั้งหมดออกไป (App, run_server, keep_alive)
# -----------------------------------------------------------------------------

# --- ⚙️ ตัวแปรการตั้งค่าหลัก (Global Settings) ---
DB_NAME = 'school_data.db'
STAFF_ROLE_NAME = 'Student Council'        
START_ROLE_NAME = 'newbie'                 
WELCOME_CHANNEL_ID = 1441105584056303780   # รหัส Channel ต้อนรับ
STAFF_ALERT_CHANNEL_ID = 1441128039416201246 # รหัส Channel แจ้งเตือน Staff
# ---------------------------------------------------

# --- 📚 การตั้งค่า Bot Intents ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True 

bot = commands.Bot(command_prefix='!', intents=intents) 

# --- ฐานข้อมูล: การเชื่อมต่อและการตั้งค่าตารางหลัก (Primary Tables) ---
def connect_db():
    conn = sqlite3.connect(DB_NAME)
    # ตารางหลักสำหรับเก็บข้อมูลผู้ใช้ (user_data) และ ใบสมัคร (applications)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS user_data ( 
            user_id INTEGER PRIMARY KEY, 
            is_approved BOOLEAN DEFAULT 0
        );
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER PRIMARY KEY,
            application_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    return conn

# --- 🌟 รายการ COGS ที่ต้องโหลดทั้งหมด ---
EXTENSIONS = [
    'cogs.roles', 
    'cogs.economy', 
    'cogs.profile',
    'cogs.shop',
    'cogs.inventory',
    'cogs.rp_system',
    'cogs.data_cleanup',
    'cogs.school_activities'
]

async def load_cogs():
    """ฟังก์ชันสำหรับโหลดไฟล์ Cog ทั้งหมดจากโฟลเดอร์ cogs/"""
    for extension in EXTENSIONS:
        try:
            await bot.load_extension(extension)
            print(f'✅ โหลด Cog: {extension} สำเร็จ')
        except Exception as e:
            # หากมี Cog ใด Cog หนึ่งโหลดไม่ได้ บอทจะแจ้งเตือน
            print(f'❌ ไม่สามารถโหลด {extension} ได้: {e}')
             
@bot.event
async def on_ready():
    connect_db() # เชื่อมต่อ DB เมื่อบอทออนไลน์
    
    await bot.change_presence(activity=discord.Game(name="ดูแลระบบโรงเรียน (v.Cogs)"))
    print(f'*** {bot.user} ออนไลน์แล้ว! กำลังโหลด Cogs... ***')
    
    await load_cogs() 
    
    # ซิงค์คำสั่ง Slash (สำคัญ: ทำครั้งเดียวหลังโหลดทั้งหมด)
    await bot.tree.sync() 
    print("--- โหลดระบบทั้งหมดและซิงค์คำสั่งเสร็จสมบูรณ์ ---")
    
# --- 🛠️ คำสั่งชั่วคราวสำหรับบังคับซิงค์ Slash Commands (ใช้ซ้ำในการแก้ปัญหาเบิ้ล) ---
@bot.command(name="sync")
@commands.is_owner() 
async def sync_commands(ctx, action: str = "guild"): 
    """บังคับซิงค์ Slash Commands. ใช้ 'clear' เพื่อลบคำสั่งเก่าทั้งหมด"""
    
    if action.lower() == "clear":
        # ล้างคำสั่งเก่าทั้งหมดจาก Global API Cache
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync(guild=None)
        await ctx.send("🔥 **ล้างคำสั่งเก่าออกจาก Discord API แล้ว!** กรุณาพิมพ์ `!sync` ทันทีเพื่อลงทะเบียนคำสั่งใหม่.")
        return
        
    # Final sync: ซิงค์คำสั่งใหม่ที่ถูกต้อง
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    
    await ctx.send(f"✅ ซิงค์คำสั่ง Slash แล้ว **{len(synced)}** คำสั่ง ในเซิร์ฟเวอร์นี้")
# --------------------------------------------------------
    
# ----------------- B. ส่วนรันบอทหลัก -----------------
# 🚨 ใช้ DISCORD_TOKEN ที่อ่านจาก Replit Secrets เท่านั้น!
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN') 

if DISCORD_TOKEN is None:
    print("Error: DISCORD_TOKEN not found in Replit Secrets (Environment variables). Bot will not run.")
else:
    # 🚨 ลบการเรียก keep_alive() ออก
    bot.run(DISCORD_TOKEN) # รันบอทด้วย Token ที่อ่านจาก Secrets (ใช้ bot.run แทน client.run)
# -----------------------------------------------------
