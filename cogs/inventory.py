import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
import os
import typing 

DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"

class Inventory(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    async def my_inventory_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        conn = self._get_db()
        items = conn.execute(
            "SELECT item_name FROM inventory WHERE user_id = ? AND item_name LIKE ? LIMIT 25", 
            (interaction.user.id, f"%{current}%")
        ).fetchall()
        conn.close()
        return [app_commands.Choice(name=row[0], value=row[0]) for row in items]

    @app_commands.command(name="inventory", description="ดูกระเป๋าเก็บของและรายละเอียดสินค้า (ส่วนตัว)")
    async def inventory(self, interaction: discord.Interaction):
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.item_name, i.amount, s.description, s.image_url 
            FROM inventory i
            JOIN shop_items s ON i.item_name = s.name
            WHERE i.user_id = ?
        """, (interaction.user.id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            return await interaction.response.send_message("🎒 กระเป๋าว่างเปล่า", ephemeral=True)

        desc_list = ""
        for name, amount, _, _ in items:
            desc_list += f"🔹 **{name}** x{amount}\n"

        embed = discord.Embed(title=f"🎒 กระเป๋าของ {interaction.user.display_name}", description=desc_list, color=discord.Color.blue())
        embed.set_footer(text="เลือกไอเทมจากเมนูด้านล่างเพื่อดูรายละเอียดและรูปภาพ")

        view = InventoryView(items)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="display_item", description="อวดไอเทมแบบเน้นรูปภาพเดียว")
    @app_commands.describe(item_name="เลือกไอเทมที่จะโชว์")
    @app_commands.autocomplete(item_name=my_inventory_autocomplete)
    async def display_item(self, interaction: discord.Interaction, item_name: str):
        # Public Message
        await interaction.response.defer(ephemeral=False)
        
        conn = self._get_db()
        cursor = conn.cursor()

        data = cursor.execute("""
            SELECT s.image_url 
            FROM inventory i
            JOIN shop_items s ON i.item_name = s.name
            WHERE i.user_id = ? AND i.item_name = ?
        """, (interaction.user.id, item_name)).fetchone()
        
        # ปิด Connection ชั่วคราวก่อนส่งข้อความ
        # (เดี๋ยวเปิดใหม่ตอนบันทึก Active Display เพื่อป้องกัน Database Lock ในบางกรณี แต่จริงๆ ใช้ cursor เดิมก็ได้)
        
        if not data:
            conn.close()
            return await interaction.followup.send(f"❌ คุณไม่มีไอเทม **{item_name}** ในกระเป๋า", ephemeral=True)

        image_url = data[0]
        
        embed = discord.Embed(title=f"✨ {item_name} ✨", color=discord.Color.gold())
        embed.set_footer(text=f"Owner: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

        if image_url: embed.set_image(url=image_url)
        else: embed.description = "❌ สินค้านี้ไม่มีรูปภาพประกอบ"

        # ส่งข้อความ
        message = await interaction.followup.send(embed=embed)
        
        # [NEW] บันทึก Message ID เพื่อให้ตามลบได้เมื่อสินค้าถูกลบ
        # ต้องบันทึก: item_name, channel_id, message_id
        try:
            cursor.execute("""
                INSERT INTO active_displays (item_name, channel_id, message_id)
                VALUES (?, ?, ?)
            """, (item_name, message.channel.id, message.id))
            conn.commit()
        except Exception as e:
            print(f"Error saving active display: {e}")
        finally:
            conn.close()


# --- UI Classes ---

class InventorySelect(discord.ui.Select):
    def __init__(self, items):
        options = []
        for item in items[:25]:
            name, amount, desc, image_url = item
            short_desc = (desc[:47] + "...") if desc and len(desc) > 50 else (desc or "ไม่มีรายละเอียด")
            options.append(discord.SelectOption(label=f"{name} (มี {amount} ชิ้น)", description=short_desc, value=name))
        super().__init__(placeholder="🔍 เลือกไอเทมเพื่อดูรูปภาพ...", min_values=1, max_values=1, options=options)
        self.items_data = {item[0]: item for item in items}

    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        name, amount, desc, image_url = self.items_data[selected_name]
        embed = discord.Embed(title=f"📦 รายละเอียด: {name}", description=desc or "ไม่มีคำอธิบาย", color=discord.Color.teal())
        embed.add_field(name="จำนวนที่มี", value=f"{amount} ชิ้น")
        if image_url: embed.set_image(url=image_url)
        else: embed.set_footer(text="สินค้านี้ไม่มีรูปภาพ")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class InventoryView(discord.ui.View):
    def __init__(self, items):
        super().__init__()
        self.add_item(InventorySelect(items))

async def setup(bot: commands.Bot):
    await bot.add_cog(Inventory(bot))
