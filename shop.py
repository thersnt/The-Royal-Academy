import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
import os
import typing
import datetime
from utils import load_data, PROFILE_FILE 

DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"
SHOP_LOGO_URL = "https://iili.io/f3RXjgp.png" 

# 🚨 กำหนด Role ตามสิทธิ์การใช้งาน
ROLES_SUPERVISOR = ["Empress of TRA", "Commerce Handler"]
ROLES_SHOP_STAFF = ["Empress of TRA", "Commerce Handler", "Shop Keeper"]

class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)
        self._create_shop_tables()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _create_shop_tables(self):
        conn = self._get_db()
        cursor = conn.cursor()
        
        # 1. ตารางสินค้า
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shop_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price INTEGER NOT NULL,
                description TEXT,
                image_url TEXT,
                stock INTEGER DEFAULT -1,
                shop_name TEXT DEFAULT 'General Store'
            )
        """)
        
        try:
            cursor.execute("SELECT shop_name FROM shop_items LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE shop_items ADD COLUMN shop_name TEXT DEFAULT 'General Store'")

        # 2. ตารางกระเป๋า
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                amount INTEGER DEFAULT 1,
                FOREIGN KEY(item_name) REFERENCES shop_items(name)
            )
        """)

        # 3. ตารางบันทึกการขาย
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                item_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                shop_name TEXT DEFAULT 'Unknown'
            )
        """)
        
        try:
            cursor.execute("SELECT shop_name FROM sales_history LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE sales_history ADD COLUMN shop_name TEXT DEFAULT 'Unknown'")
        
        # 4. ตารางบันทึกข้อความ Display Item
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_displays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()

    # --- 📨 Helper: ส่งแจ้งเตือนแยกเธรด (Wallet / Inventory) ---
    async def _notify_thread(self, user: discord.Member, embed: discord.Embed, thread_type: str = 'wallet'):
        """
        thread_type: 'wallet' หรือ 'inventory'
        """
        try:
            profiles = load_data(PROFILE_FILE)
            user_id_str = str(user.id)
            
            # เลือก Key ตามประเภทที่ต้องการส่ง
            if thread_type == 'inventory':
                thread_id = profiles.get(user_id_str, {}).get('inventory_thread_id')
            else:
                thread_id = profiles.get(user_id_str, {}).get('wallet_thread_id')
            
            if thread_id:
                thread = self.bot.get_channel(int(thread_id))
                if thread: 
                    await thread.send(embed=embed)
                else:
                    print(f"Could not find channel for thread ID: {thread_id}")
            else:
                print(f"No {thread_type} thread ID found for user {user.display_name}")
                
        except Exception as e:
            print(f"Failed to send shop notification to {thread_type} thread: {e}")

    # --- 🛠️ Shop Management Commands ---

    @app_commands.command(name="shop_add", description="[Staff] เพิ่มสินค้าใหม่ลงร้านค้า")
    @app_commands.describe(name="ชื่อสินค้า", shop_name="ชื่อร้านค้า", price="ราคา", description="รายละเอียด", image_url="ลิงก์รูป", stock="จำนวน (-1 คือไม่จำกัด)")
    async def shop_add(self, interaction: discord.Interaction, name: str, shop_name: str, price: int, description: str, image_url: str = None, stock: int = -1):
        if not any(r.name in ROLES_SHOP_STAFF for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์จัดการสินค้า", ephemeral=True)

        conn = self._get_db()
        try:
            conn.execute("""
                INSERT INTO shop_items (name, shop_name, price, description, image_url, stock) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, shop_name, price, description, image_url, stock))
            conn.commit()
            
            embed = discord.Embed(title="✅ เพิ่มสินค้าเรียบร้อย", color=discord.Color.green())
            embed.description = f"**{name}**\nร้าน: {shop_name}\nราคา: `{price:,} {CURRENCY_SYMBOL}`"
            if image_url: embed.set_thumbnail(url=image_url)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except sqlite3.IntegrityError:
            await interaction.response.send_message(f"❌ มีสินค้านี้ชื่อ **{name}** อยู่แล้ว (หากต้องการเติมของ ให้ใช้ `/shop_restock`)", ephemeral=True)
        finally:
            conn.close()

    async def shop_item_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        conn = self._get_db()
        items = conn.execute("SELECT name FROM shop_items WHERE name LIKE ? LIMIT 25", (f"%{current}%",)).fetchall()
        conn.close()
        return [app_commands.Choice(name=row[0], value=row[0]) for row in items]

    @app_commands.command(name="shop_edit", description="[Staff] แก้ไขรายละเอียดสินค้า")
    @app_commands.autocomplete(name=shop_item_autocomplete)
    async def shop_edit(self, interaction: discord.Interaction, name: str, new_name: str = None, price: int = -1, description: str = None, image_url: str = None, stock: int = -999, shop_name: str = None):
        if not any(r.name in ROLES_SHOP_STAFF for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์จัดการสินค้า", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        item = cursor.execute("SELECT id FROM shop_items WHERE name = ?", (name,)).fetchone()
        if not item:
            conn.close()
            return await interaction.response.send_message(f"❌ ไม่พบสินค้าชื่อ **{name}**", ephemeral=True)

        updates = []
        params = []
        if new_name:
            updates.append("name = ?")
            params.append(new_name)
        if price != -1:
            updates.append("price = ?")
            params.append(price)
        if description:
            updates.append("description = ?")
            params.append(description)
        if image_url:
            updates.append("image_url = ?")
            params.append(image_url)
        if stock != -999:
            updates.append("stock = ?")
            params.append(stock)
        if shop_name:
            updates.append("shop_name = ?")
            params.append(shop_name)

        if not updates:
            conn.close()
            return await interaction.response.send_message("⚠️ คุณไม่ได้ระบุข้อมูลที่ต้องการแก้ไข", ephemeral=True)

        params.append(name)

        try:
            cursor.execute(f"UPDATE shop_items SET {', '.join(updates)} WHERE name = ?", params)
            if new_name:
                cursor.execute("UPDATE inventory SET item_name = ? WHERE item_name = ?", (new_name, name))
                cursor.execute("UPDATE active_displays SET item_name = ? WHERE item_name = ?", (new_name, name))
            conn.commit()
            
            msg = f"✅ แก้ไขสินค้า **{name}** เรียบร้อยแล้ว\n"
            if new_name: msg += f"• เปลี่ยนชื่อเป็น: **{new_name}**\n"
            
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ เกิดข้อผิดพลาดในการแก้ไข", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="shop_restock", description="[Staff] เติมสต็อกสินค้าที่มีอยู่แล้ว")
    async def shop_restock(self, interaction: discord.Interaction, name: str, amount: int):
        if not any(r.name in ROLES_SHOP_STAFF for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์จัดการสินค้า", ephemeral=True)
        if amount <= 0: return await interaction.response.send_message("❌ จำนวนต้องมากกว่า 0", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        item = cursor.execute("SELECT stock FROM shop_items WHERE name = ?", (name,)).fetchone()
        if not item:
            conn.close()
            return await interaction.response.send_message(f"❌ ไม่พบสินค้าชื่อ **{name}**", ephemeral=True)
        
        cursor.execute("UPDATE shop_items SET stock = stock + ? WHERE name = ?", (amount, name))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"📦 เติมสต็อก **{name}** เรียบร้อย", ephemeral=True)

    @app_commands.command(name="shop_remove", description="[Staff] ลบสินค้า")
    async def shop_remove(self, interaction: discord.Interaction, name: str):
        if not any(r.name in ROLES_SHOP_STAFF for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์จัดการสินค้า", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM shop_items WHERE name = ?", (name,))
        if not cursor.fetchone():
            conn.close()
            return await interaction.followup.send(f"❌ ไม่พบสินค้าชื่อ **{name}**", ephemeral=True)

        # ลบข้อความ Display เก่า
        cursor.execute("SELECT channel_id, message_id FROM active_displays WHERE item_name = ?", (name,))
        for cid, mid in cursor.fetchall():
            try:
                ch = self.bot.get_channel(cid)
                if ch: await (await ch.fetch_message(mid)).delete()
            except: pass

        cursor.execute("DELETE FROM active_displays WHERE item_name = ?", (name,))
        cursor.execute("DELETE FROM inventory WHERE item_name = ?", (name,))
        cursor.execute("DELETE FROM shop_items WHERE name = ?", (name,))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🗑️ ลบสินค้า **{name}** เรียบร้อย", ephemeral=True)

    # --- 📜 Supervisor Commands ---

    @app_commands.command(name="sales_history", description="[Supervisor] ดูประวัติการขาย")
    async def sales_history(self, interaction: discord.Interaction):
        if not any(r.name in ROLES_SUPERVISOR for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ดูข้อมูลนี้", ephemeral=True)

        conn = self._get_db()
        logs = conn.execute("SELECT user_name, item_name, price, timestamp, shop_name FROM sales_history ORDER BY id DESC LIMIT 50").fetchall()
        conn.close()

        if not logs: return await interaction.response.send_message("📭 ยังไม่มีประวัติการขาย", ephemeral=True)

        text_logs = ""
        for user, item, price, ts, shop in logs:
            dt = datetime.datetime.fromisoformat(ts).strftime("%d/%m %H:%M")
            shop_display = f" (จาก {shop})" if shop and shop != 'Unknown' else ""
            text_logs += f"`{dt}`: **{user}** ซื้อ **{item}** ({price:,} {CURRENCY_SYMBOL}){shop_display}\n"
        
        embed = discord.Embed(title="📜 ประวัติการขาย (50 ล่าสุด)", description=text_logs, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="clear_sales_history", description="[Supervisor] ล้างประวัติการขาย")
    async def clear_sales_history(self, interaction: discord.Interaction):
        if not any(r.name in ROLES_SUPERVISOR for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ลบข้อมูลนี้", ephemeral=True)
        conn = self._get_db()
        conn.execute("DELETE FROM sales_history")
        conn.commit()
        conn.close()
        await interaction.response.send_message("🧹 ล้างประวัติการขายเรียบร้อย", ephemeral=True)

    # --- 🛍️ Shop & Buy Commands ---

    @app_commands.command(name="shop", description="ดูรายการสินค้า")
    async def shop(self, interaction: discord.Interaction):
        conn = self._get_db()
        shops = [r[0] for r in conn.execute("SELECT DISTINCT shop_name FROM shop_items ORDER BY shop_name").fetchall()]
        items = conn.execute("SELECT name, price, stock, shop_name FROM shop_items ORDER BY shop_name").fetchall()
        conn.close()

        if not items: return await interaction.response.send_message("🏪 ยังไม่มีสินค้าวางขาย", ephemeral=True)

        embed = discord.Embed(title="🛒 Shopping Center", description="ใช้เมนูด้านล่างเพื่อเลือกร้านค้า หรือพิมพ์ `/buy` เพื่อซื้อ", color=discord.Color.gold())
        embed.set_thumbnail(url=SHOP_LOGO_URL) 

        current_shop = None
        shop_text = ""
        for name, price, stock, shop_name in items:
            if shop_name != current_shop:
                if current_shop: embed.add_field(name=f"🛖 {current_shop}", value=shop_text, inline=False)
                current_shop = shop_name
                shop_text = ""
            stock_str = "♾️" if stock == -1 else f"({stock})"
            shop_text += f"• **{name}** - `{price:,} {CURRENCY_SYMBOL}` {stock_str}\n"
        if current_shop: embed.add_field(name=f"🛖 {current_shop}", value=shop_text, inline=False)

        await interaction.response.send_message(embed=embed, view=ShopFilterView(shops, self.db_path))

    @app_commands.command(name="buy", description="เลือกซื้อสินค้า")
    async def buy(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        conn = self._get_db()
        shops = conn.execute("SELECT DISTINCT shop_name FROM shop_items").fetchall()
        conn.close()

        if not shops: return await interaction.followup.send("❌ ตอนนี้ยังไม่มีร้านค้าเปิดทำการ", ephemeral=True)
        
        embed = discord.Embed(title="🏪 ยินดีต้อนรับสู่ศูนย์การค้า", description="โปรดเลือก **ร้านค้า** ที่คุณต้องการเข้าชมด้านล่าง", color=discord.Color.green())
        await interaction.followup.send(embed=embed, view=ShopSelectView(shops, self.db_path, self._notify_thread))

    async def my_inventory_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        conn = self._get_db()
        items = conn.execute("SELECT item_name FROM inventory WHERE user_id = ? AND item_name LIKE ? LIMIT 25", (interaction.user.id, f"%{current}%")).fetchall()
        conn.close()
        return [app_commands.Choice(name=row[0], value=row[0]) for row in items]

    @app_commands.command(name="transfer_item", description="โอนไอเทมให้ผู้เล่นอื่น")
    @app_commands.autocomplete(item_name=my_inventory_autocomplete)
    async def transfer_item(self, interaction: discord.Interaction, recipient: discord.Member, item_name: str, amount: int = 1):
        await interaction.response.defer(ephemeral=False) 
        if amount <= 0: return await interaction.followup.send("❌ จำนวนต้องมากกว่า 0", ephemeral=True)
        if recipient.id == interaction.user.id: return await interaction.followup.send("❌ ส่งให้ตัวเองไม่ได้", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        sender_item = cursor.execute("SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?", (interaction.user.id, item_name)).fetchone()
        
        if not sender_item or sender_item[0] < amount:
            conn.close()
            return await interaction.followup.send(f"❌ คุณมีไอเทมไม่เพียงพอ", ephemeral=True)

        try:
            new_sender_amount = sender_item[0] - amount
            if new_sender_amount == 0:
                cursor.execute("DELETE FROM inventory WHERE user_id = ? AND item_name = ?", (interaction.user.id, item_name))
            else:
                cursor.execute("UPDATE inventory SET amount = ? WHERE user_id = ? AND item_name = ?", (new_sender_amount, interaction.user.id, item_name))

            recipient_item = cursor.execute("SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?", (recipient.id, item_name)).fetchone()
            if recipient_item:
                cursor.execute("UPDATE inventory SET amount = amount + ? WHERE user_id = ? AND item_name = ?", (amount, recipient.id, item_name))
            else:
                cursor.execute("INSERT INTO inventory (user_id, item_name, amount) VALUES (?, ?, ?)", (recipient.id, item_name, amount))
            conn.commit()

            embed = discord.Embed(description=f"🎁 **{interaction.user.mention}** ส่ง **{item_name}** x{amount} ให้ {recipient.mention}!", color=discord.Color.blue())
            await interaction.followup.send(embed=embed)
            
            # แจ้งเตือนเข้า Inventory Thread ของผู้รับ
            thread_embed = discord.Embed(title="🎁 คุณได้รับของขวัญ!", color=discord.Color.magenta(), timestamp=datetime.datetime.now())
            thread_embed.description = f"จาก: **{interaction.user.display_name}**\nไอเทม: **{item_name}** x{amount}"
            item_info = cursor.execute("SELECT image_url FROM shop_items WHERE name = ?", (item_name,)).fetchone()
            if item_info and item_info[0]: thread_embed.set_thumbnail(url=item_info[0])
            
            # ใช้ 'inventory' เพื่อส่งเข้าเธรดเก็บของ
            await self._notify_thread(recipient, thread_embed, 'inventory')

        except Exception as e:
            conn.rollback()
            print(f"Transfer Error: {e}")
            await interaction.followup.send("❌ เกิดข้อผิดพลาด", ephemeral=True)
        finally:
            conn.close()

# --- UI Classes ---

class ShopFilterSelect(discord.ui.Select):
    def __init__(self, shops, db_path):
        self.db_path = db_path
        options = [discord.SelectOption(label="แสดงทั้งหมด (All Shops)", value="all", emoji="🌟")]
        for shop in shops:
            options.append(discord.SelectOption(label=shop, value=shop, emoji="🛖"))
        super().__init__(placeholder="👀 เลือกร้านค้าที่ต้องการดู...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_value = self.values[0]
        conn = sqlite3.connect(self.db_path)
        
        embed = discord.Embed(title="🛒 Shopping Center", color=discord.Color.gold())
        embed.set_thumbnail(url=SHOP_LOGO_URL) 
        embed.description = "ใช้เมนูด้านล่างเพื่อเลือกร้านค้า หรือพิมพ์ `/buy` เพื่อซื้อ"

        if selected_value == "all":
            items = conn.execute("SELECT name, price, stock, shop_name FROM shop_items ORDER BY shop_name").fetchall()
            current_shop, shop_text = None, ""
            for name, price, stock, shop_name in items:
                if shop_name != current_shop:
                    if current_shop: embed.add_field(name=f"🛖 {current_shop}", value=shop_text, inline=False)
                    current_shop = shop_name
                    shop_text = ""
                stock_str = "♾️" if stock == -1 else f"({stock})"
                shop_text += f"• **{name}** - `{price:,} {CURRENCY_SYMBOL}` {stock_str}\n"
            if current_shop: embed.add_field(name=f"🛖 {current_shop}", value=shop_text, inline=False)
        else:
            items = conn.execute("SELECT name, price, stock FROM shop_items WHERE shop_name = ?", (selected_value,)).fetchall()
            shop_text = ""
            for name, price, stock in items:
                stock_str = "♾️" if stock == -1 else f"({stock})"
                shop_text += f"• **{name}** - `{price:,} {CURRENCY_SYMBOL}` {stock_str}\n"
            if not shop_text: shop_text = "ไม่มีสินค้า"
            embed.add_field(name=f"🛖 {selected_value}", value=shop_text, inline=False)
        
        conn.close()
        await interaction.response.edit_message(embed=embed)

class ShopFilterView(discord.ui.View):
    def __init__(self, shops, db_path):
        super().__init__(timeout=None)
        self.add_item(ShopFilterSelect(shops, db_path))

class ShopSelect(discord.ui.Select):
    def __init__(self, shops, db_path, notify_func):
        self.db_path = db_path
        self.notify_func = notify_func
        options = [discord.SelectOption(label=shop[0], value=shop[0], emoji="🛖") for shop in shops]
        super().__init__(placeholder="🛒 เลือกร้านค้าเพื่อซื้อของ...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_shop = self.values[0]
        conn = sqlite3.connect(self.db_path)
        items = conn.execute("SELECT name, price, stock, description FROM shop_items WHERE shop_name = ?", (selected_shop,)).fetchall()
        conn.close()
        
        if not items: return await interaction.response.send_message(f"❌ ร้าน **{selected_shop}** ไม่มีสินค้าในขณะนี้", ephemeral=True)
        view = ItemSelectView(items, selected_shop, self.db_path, self.notify_func)
        embed = discord.Embed(title=f"🛖 ยินดีต้อนรับสู่ {selected_shop}", description="เลือก **สินค้า** ที่คุณต้องการซื้อ", color=discord.Color.gold())
        await interaction.response.edit_message(embed=embed, view=view)

class ShopSelectView(discord.ui.View):
    def __init__(self, shops, db_path, notify_func):
        super().__init__()
        self.add_item(ShopSelect(shops, db_path, notify_func))

class ItemSelect(discord.ui.Select):
    def __init__(self, items, shop_name, db_path, notify_func):
        self.db_path = db_path
        self.notify_func = notify_func
        self.shop_name = shop_name
        options = []
        for item in items[:25]:
            name, price, stock, desc = item
            stock_str = "♾️" if stock == -1 else f"{stock} ชิ้น"
            short_desc = (desc[:47] + "...") if desc and len(desc) > 50 else (desc or "ไม่มีรายละเอียด")
            options.append(discord.SelectOption(label=f"{name} ({price:,} {CURRENCY_SYMBOL})", description=f"Stock: {stock_str} | {short_desc}", value=name))
        super().__init__(placeholder="เลือกสินค้าที่จะซื้อ...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        item_name = self.values[0]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            item = cursor.execute("SELECT id, price, stock, image_url FROM shop_items WHERE name = ?", (item_name,)).fetchone()
            if not item: return await interaction.response.send_message("❌ ไม่พบสินค้านี้", ephemeral=True)
            item_id, price, stock, image_url = item
            if stock != -1 and stock <= 0: return await interaction.response.send_message("❌ สินค้าหมด", ephemeral=True)

            balance = cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)).fetchone()
            balance = balance[0] if balance else 0
            if balance < price: return await interaction.response.send_message(f"❌ เงินไม่พอ (ขาด {price-balance:,} {CURRENCY_SYMBOL})", ephemeral=True)

            cursor.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (price, interaction.user.id))
            if stock != -1: cursor.execute("UPDATE shop_items SET stock = stock - 1 WHERE id = ?", (item_id,))
            
            has_item = cursor.execute("SELECT amount FROM inventory WHERE user_id = ? AND item_name = ?", (interaction.user.id, item_name)).fetchone()
            if has_item: cursor.execute("UPDATE inventory SET amount = amount + 1 WHERE user_id = ? AND item_name = ?", (interaction.user.id, item_name))
            else: cursor.execute("INSERT INTO inventory (user_id, item_name, amount) VALUES (?, ?, 1)", (interaction.user.id, item_name))

            cursor.execute("INSERT INTO sales_history (user_id, user_name, item_name, price, timestamp, shop_name) VALUES (?, ?, ?, ?, ?, ?)", 
                           (interaction.user.id, interaction.user.display_name, item_name, price, datetime.datetime.now(datetime.timezone.utc).isoformat(), self.shop_name))
            conn.commit()

            # Public Message
            public_embed = discord.Embed(description=f"✅ **สั่งซื้อสำเร็จ:** **{item_name}**\nราคา: `{price:,} {CURRENCY_SYMBOL}`", color=discord.Color.green())
            if image_url: public_embed.set_thumbnail(url=image_url)
            await interaction.response.edit_message(embed=public_embed, view=None)

            # 1. 🧾 Receipt -> Wallet Thread (Type: 'wallet')
            thread_receipt = discord.Embed(title="🧾 ใบเสร็จการสั่งซื้อ", color=discord.Color.gold(), timestamp=datetime.datetime.now())
            thread_receipt.add_field(name="สินค้า", value=item_name, inline=True)
            thread_receipt.add_field(name="ร้านค้า", value=self.shop_name, inline=True)
            thread_receipt.add_field(name="ราคา", value=f"{price:,} {CURRENCY_SYMBOL}", inline=True)
            if image_url: thread_receipt.set_thumbnail(url=image_url)
            await self.notify_func(interaction.user, thread_receipt, 'wallet')
            
            # 2. ✨ Display Item -> Inventory Thread (Type: 'inventory')
            thread_display = discord.Embed(title=f"✨ {item_name} ✨", color=discord.Color.gold())
            if image_url: thread_display.set_image(url=image_url)
            else: thread_display.description = "สินค้าไม่มีรูปภาพ"
            thread_display.set_footer(text=f"Owner: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            await self.notify_func(interaction.user, thread_display, 'inventory')

        except Exception as e:
            conn.rollback()
            print(f"Buy UI Error: {e}")
            await interaction.response.send_message("❌ เกิดข้อผิดพลาด", ephemeral=True)
        finally:
            conn.close()

class ItemSelectView(discord.ui.View):
    def __init__(self, items, shop_name, db_path, notify_func):
        super().__init__()
        self.add_item(ItemSelect(items, shop_name, db_path, notify_func))

async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))