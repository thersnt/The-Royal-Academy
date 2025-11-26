import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
import datetime
from utils import load_data, PROFILE_FILE 

DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"
SHOP_LOGO = "https://iili.io/f3RXjgp.png"
SHOP_ADMIN_ROLES = ["Empress of TRA", "Commerce Handler", "Shop Keeper"]
SUPERVISOR_ROLES = ["Empress of TRA", "Commerce Handler"]

class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS shop_items (id INTEGER PRIMARY KEY, name TEXT UNIQUE, price INTEGER, description TEXT, image_url TEXT, stock INTEGER DEFAULT -1, shop_name TEXT DEFAULT 'General Store')")
            await db.execute("CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, user_id INTEGER, item_name TEXT, amount INTEGER DEFAULT 1)")
            await db.execute("CREATE TABLE IF NOT EXISTS sales_history (id INTEGER PRIMARY KEY, user_id INTEGER, user_name TEXT, item_name TEXT, price INTEGER, timestamp TEXT, shop_name TEXT DEFAULT 'Unknown')")
            await db.execute("CREATE TABLE IF NOT EXISTS active_displays (id INTEGER PRIMARY KEY, item_name TEXT, channel_id INTEGER, message_id INTEGER)")
            await db.commit()

    async def _notify(self, user, embed):
        try:
            p = load_data(PROFILE_FILE)
            wid = p.get(str(user.id), {}).get('wallet_thread_id')
            if wid:
                ch = self.bot.get_channel(int(wid))
                if ch: await ch.send(embed=embed)
        except: pass

    @app_commands.command(name="shop_add")
    async def add(self, interaction, name: str, shop_name: str, price: int, description: str, image_url: str = None, stock: int = -1):
        if not any(r.name in SHOP_ADMIN_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("INSERT INTO shop_items (name, shop_name, price, description, image_url, stock) VALUES (?,?,?,?,?,?)", (name, shop_name, price, description, image_url, stock))
                await db.commit()
                await interaction.response.send_message(f"✅ เพิ่มสินค้า **{name}** แล้ว", ephemeral=True)
            except: await interaction.response.send_message("❌ มีสินค้านี้แล้ว", ephemeral=True)

    @app_commands.command(name="shop_restock")
    async def restock(self, interaction, name: str, amount: int):
        if not any(r.name in SHOP_ADMIN_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE shop_items SET stock = stock + ? WHERE name = ?", (amount, name))
            await db.commit()
        await interaction.response.send_message(f"📦 เติมสต็อก {name} +{amount}", ephemeral=True)

    @app_commands.command(name="shop_remove")
    async def remove(self, interaction, name: str):
        if not any(r.name in SHOP_ADMIN_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Delete Displays
            async with db.execute("SELECT channel_id, message_id FROM active_displays WHERE item_name=?", (name,)) as c:
                displays = await c.fetchall()
            for cid, mid in displays:
                try: await (self.bot.get_channel(cid).get_partial_message(mid)).delete()
                except: pass
            
            await db.execute("DELETE FROM active_displays WHERE item_name=?", (name,))
            await db.execute("DELETE FROM inventory WHERE item_name=?", (name,))
            await db.execute("DELETE FROM shop_items WHERE name=?", (name,))
            await db.commit()
        await interaction.followup.send(f"🗑️ ลบสินค้า {name} และข้อมูลที่เกี่ยวข้องแล้ว", ephemeral=True)

    @app_commands.command(name="shop")
    async def shop(self, interaction):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT DISTINCT shop_name FROM shop_items") as c: shops = [r[0] for r in await c.fetchall()]
        
        if not shops: return await interaction.response.send_message("ร้านค้าปิดปรับปรุง", ephemeral=True)
        view = ShopSelectView(shops, self.db_path, self._notify)
        embed = discord.Embed(title="🛒 Shopping Center", description="เลือกร้านค้าด้านล่าง", color=discord.Color.gold())
        embed.set_thumbnail(url=SHOP_LOGO)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="buy")
    async def buy_cmd(self, interaction):
        await self.shop.callback(interaction) # Reuse logic

    @app_commands.command(name="sales_history")
    async def history(self, interaction):
        if not any(r.name in SUPERVISOR_ROLES for r in interaction.user.roles): return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_name, item_name, price, timestamp, shop_name FROM sales_history ORDER BY id DESC LIMIT 50") as c:
                logs = await c.fetchall()
        
        txt = ""
        for u, i, p, t, s in logs:
            dt = datetime.datetime.fromisoformat(t).strftime("%d/%m %H:%M")
            txt += f"`{dt}`: **{u}** ซื้อ **{i}** ({p} R) จาก {s}\n"
        
        await interaction.response.send_message(embed=discord.Embed(title="📜 Sales History", description=txt or "ว่างเปล่า", color=discord.Color.orange()), ephemeral=True)

class ShopSelectView(discord.ui.View):
    def __init__(self, shops, db, notify):
        super().__init__()
        self.add_item(ShopSelect(shops, db, notify))

class ShopSelect(discord.ui.Select):
    def __init__(self, shops, db, notify):
        self.db = db
        self.notify = notify
        options = [discord.SelectOption(label=s, value=s, emoji="🛖") for s in shops]
        super().__init__(placeholder="เลือกร้าน...", options=options)

    async def callback(self, interaction):
        shop = self.values[0]
        async with aiosqlite.connect(self.db) as db:
            async with db.execute("SELECT name, price, stock, description FROM shop_items WHERE shop_name=?", (shop,)) as c:
                items = await c.fetchall()
        
        if not items: return await interaction.response.send_message("ไม่มีสินค้า", ephemeral=True)
        view = ItemSelectView(items, shop, self.db, self.notify)
        await interaction.response.edit_message(embed=discord.Embed(title=f"🛖 {shop}", description="เลือกสินค้าที่จะซื้อ", color=discord.Color.gold()), view=view)

class ItemSelectView(discord.ui.View):
    def __init__(self, items, shop, db, notify):
        super().__init__()
        self.add_item(ItemSelect(items, shop, db, notify))

class ItemSelect(discord.ui.Select):
    def __init__(self, items, shop, db, notify):
        self.db = db
        self.notify = notify
        self.shop = shop
        options = []
        for n, p, s, d in items[:25]:
            stock = "♾️" if s == -1 else f"{s} ชิ้น"
            options.append(discord.SelectOption(label=f"{n} ({p} R)", description=f"Stock: {stock}", value=n))
        super().__init__(placeholder="เลือกสินค้า...", options=options)

    async def callback(self, interaction):
        name = self.values[0]
        async with aiosqlite.connect(self.db) as db:
            # Check item
            async with db.execute("SELECT id, price, stock, image_url FROM shop_items WHERE name=?", (name,)) as c:
                item = await c.fetchone()
            if not item: return await interaction.response.send_message("สินค้าหมด/ถูกลบ", ephemeral=True)
            iid, price, stock, img = item

            if stock != -1 and stock <= 0: return await interaction.response.send_message("สินค้าหมด", ephemeral=True)

            # Check money
            async with db.execute("SELECT balance FROM royals WHERE user_id=?", (interaction.user.id,)) as c:
                res = await c.fetchone()
                bal = res[0] if res else 0
            if bal < price: return await interaction.response.send_message("เงินไม่พอ", ephemeral=True)

            # Transact
            await db.execute("UPDATE royals SET balance=balance-? WHERE user_id=?", (price, interaction.user.id))
            if stock != -1: await db.execute("UPDATE shop_items SET stock=stock-1 WHERE id=?", (iid,))
            
            # Add inventory
            async with db.execute("SELECT amount FROM inventory WHERE user_id=? AND item_name=?", (interaction.user.id, name)) as c:
                has = await c.fetchone()
            if has: await db.execute("UPDATE inventory SET amount=amount+1 WHERE user_id=? AND item_name=?", (interaction.user.id, name))
            else: await db.execute("INSERT INTO inventory (user_id, item_name, amount) VALUES (?,?,1)", (interaction.user.id, name))
            
            # Log
            await db.execute("INSERT INTO sales_history (user_id, user_name, item_name, price, timestamp, shop_name) VALUES (?,?,?,?,?,?)", 
                             (interaction.user.id, interaction.user.display_name, name, price, datetime.datetime.now().isoformat(), self.shop))
            await db.commit()

            embed = discord.Embed(description=f"🛍️ ซื้อ **{name}** สำเร็จ!", color=discord.Color.green())
            if img: embed.set_thumbnail(url=img)
            await interaction.response.edit_message(embed=embed, view=None)

            # Notify
            rec = discord.Embed(title="🧾 ใบเสร็จ", color=discord.Color.gold())
            rec.add_field(name="สินค้า", value=name)
            rec.add_field(name="ราคา", value=f"{price} R")
            if img: rec.set_thumbnail(url=img)
            await self.notify(interaction.user, rec)

async def setup(bot):
    await bot.add_cog(Shop(bot))

