import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
# 🚨 เปลี่ยนไปใช้ aiosqlite แทน sqlite3
import aiosqlite 

# ----------------- A. ส่วน Keep Alive ถูกลบแล้ว (ถูกต้อง) --------------------

# --- ⚙️ ตัวแปรการตั้งค่าหลัก (Global Settings) ---
DB_NAME = 'school_data.db'
# ... (ตัวแปรอื่น ๆ)

# --- 📚 การตั้งค่า Bot Intents ---
# ... (ส่วน Intents และ bot = commands.Bot)

# --- ฐานข้อมูล: การเชื่อมต่อและการตั้งค่าตารางหลัก (Primary Tables) ---
async def connect_db():
    # 🚨 ใช้ aiosqlite.connect() แทน sqlite3.connect()
    conn = await aiosqlite.connect(DB_NAME)
    
    # 🚨 ใช้ await conn.execute() สำหรับคำสั่งฐานข้อมูล
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS user_data ( 
            user_id INTEGER PRIMARY KEY, 
            is_approved BOOLEAN DEFAULT 0
        );
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER PRIMARY KEY,
            application_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    await conn.commit()
    # 🚨 ส่งคืนค่า conn ที่เป็น Async Connection
    return conn

# --- 🌟 รายการ COGS ที่ต้องโหลดทั้งหมด ---
# ... (EXTENSIONS)

async def load_cogs():
# ... (ไม่ต้องแก้ไข)
    
@bot.event
async def on_ready():
    # 🚨 ต้องใช้ await ก่อน connect_db() เพราะตอนนี้มันเป็น Async แล้ว
    await connect_db() 
    
    await bot.change_presence(activity=discord.Game(name="ดูแลระบบโรงเรียน (v.Cogs)"))
    print(f'*** {bot.user} ออนไลน์แล้ว! กำลังโหลด Cogs... ***')
    
    await load_cogs() 
    
    # ซิงค์คำสั่ง Slash (สำคัญ: ทำครั้งเดียวหลังโหลดทั้งหมด)
    await bot.tree.sync() 
    print("--- โหลดระบบทั้งหมดและซิงค์คำสั่งเสร็จสมบูรณ์ ---")

# ... (คำสั่ง !sync)
    
# ----------------- B. ส่วนรันบอทหลัก -----------------
# ... (ส่วนรันบอทหลัก)
