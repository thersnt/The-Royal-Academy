import json
import os
import asyncio
from typing import Dict, Any

LOCK = asyncio.Lock()

# --- ⚙️ FILE PATH CONSTANTS (REVERTED) ---
BALANCE_FILE = 'balances.json'
PROFILE_FILE = 'profiles.json'
INVENTORY_FILE = 'inventory.json'
SHOPS_FILE = 'shops.json' # Master list of items (BACK TO SINGLE ITEM FILE)
# ------------------------------------------

def _get_absolute_path(filename: str) -> str:
    """Helper เพื่อให้ได้เส้นทางที่แน่นอนของไฟล์ข้อมูลใน Root Directory"""
    return os.path.join(os.getcwd(), filename)


def load_data(filename: str) -> Dict[str, Any]:
    """Loads data from a JSON file using absolute path."""
    filepath = _get_absolute_path(filename)
    
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

async def save_data(data: Dict[str, Any], filename: str):
    """Saves data to a JSON file asynchronously and safely."""
    async with LOCK:
        await asyncio.to_thread(_save_sync, data, filename)

def _save_sync(data: Dict[str, Any], filename: str):
    """Synchronous file writing for asyncio.to_thread"""
    filepath = _get_absolute_path(filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def ensure_balance_exists(user_id: int, balances: Dict[str, Any]):
    """ตรวจสอบและสร้างบัญชี Royals ด้วยยอดเงิน 0 R ถ้ายังไม่มี"""
    user_id_str = str(user_id)
    if user_id_str not in balances:
        balances[user_id_str] = 0