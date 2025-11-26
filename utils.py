import os

# --- ⚙️ CONSTANTS ---
# เก็บชื่อไฟล์ Database ไว้เรียกใช้กลาง
DB_NAME = 'school_data.db'

# เก็บค่าคงที่อื่นๆ ที่ใช้ร่วมกัน
PROFILE_FILE = 'data/profiles.json' # เก็บไว้กัน Error import แต่ไม่ได้ใช้จริง
BALANCE_FILE = 'data/balances.json' # เก็บไว้กัน Error import แต่ไม่ได้ใช้จริง

def get_db_path():
    """คืนค่า path เต็มของ database"""
    return os.path.join(os.getcwd(), DB_NAME)

# --- ฟังก์ชัน JSON เดิม (เก็บไว้เผื่อโค้ดเก่าเรียกใช้ แต่ไม่แนะนำให้ใช้เก็บข้อมูลสำคัญ) ---
import json
import asyncio
from typing import Dict, Any

LOCK = asyncio.Lock()

def _get_absolute_path(filename: str) -> str:
    return os.path.join(os.getcwd(), filename)

def load_data(filename: str) -> Dict[str, Any]:
    filepath = _get_absolute_path(filename)
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

async def save_data(data: Dict[str, Any], filename: str):
    # ⚠️ คำเตือน: บน Render ไฟล์นี้จะหายไปเมื่อ Restart
    async with LOCK:
        await asyncio.to_thread(_save_sync, data, filename)

def _save_sync(data: Dict[str, Any], filename: str):
    filepath = _get_absolute_path(filename)
    # สร้างโฟลเดอร์ data ถ้ายังไม่มี
    os.makedirs(os.path.dirname(filepath), exist_ok=True) 
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
