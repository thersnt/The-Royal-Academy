import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
from utils import load_data, PROFILE_FILE

DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"

class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def _get_user_inventory(self, uid):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT i.item_name, i.amount, s.description, s.image_url 
                FROM inventory i JOIN shop_items s ON i.item_name = s.name 
                WHERE i.user_id = ?
            """, (uid,)) as c:
                return await c.fetchall()

    async def item_autocomplete(self, interaction, current: str):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT item_name FROM inventory WHERE user_id=? AND item_name LIKE ? LIMIT 25", (interaction.user.id, f"%{current}%")) as c:
                items = await c.fetchall()
        return [app_commands.Choice(name=i[0], value=i[0]) for i in items]

    @app_commands.command(name="inventory")
    async def inventory(self, interaction):
        items = await self._get_user_inventory(interaction.user.id)
        if not items: return await interaction.response.send_message("🎒 กระเป๋าว่างเปล่า", ephemeral=True)

        desc = ""
        for n, a, d, i in items: desc += f"🔹 **{n}** x{a}\n"
        
        embed = discord.Embed(title=f"🎒 กระเป๋าของ {interaction.user.display_name}", description=desc, color=discord.Color.blue())
        view = InventoryView(items)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="display_item")
    @app_commands.autocomplete(item_name=item_autocomplete)
    async def display(self, interaction, item_name: str):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT s.image_url FROM inventory i JOIN shop_items s ON i.item_name=s.name WHERE i.user_id=? AND i.item_name=?", (interaction.user.id, item_name)) as c:
                res = await c.fetchone()
        
        if not res: return await interaction.response.send_message("❌ ไม่มีไอเทมนี้", ephemeral=True)
        
        embed = discord.Embed(title=f"✨ {item_name} ✨", color=discord.Color.gold())
        if res[0]: embed.set_image(url=res[0])
        else: embed.description = "ไม่มีรูปภาพ"
        embed.set_footer(text=f"Owner: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        msg = await interaction.response.send_message(embed=embed)
        
        # Log display
        async with aiosqlite.connect(self.db_path) as db:
            msg_obj = await interaction.original_response()
            await db.execute("INSERT INTO active_displays (item_name, channel_id, message_id) VALUES (?,?,?)", (item_name, interaction.channel.id, msg_obj.id))
            await db.commit()

    @app_commands.command(name="transfer_item")
    @app_commands.autocomplete(item_name=item_autocomplete)
    async def transfer_item(self, interaction, recipient: discord.Member, item_name: str, amount: int = 1):
        if amount <= 0 or recipient.id == interaction.user.id: return await interaction.response.send_message("❌ ทำรายการไม่ได้", ephemeral=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT amount FROM inventory WHERE user_id=? AND item_name=?", (interaction.user.id, item_name)) as c:
                res = await c.fetchone()
            
            if not res or res[0] < amount: return await interaction.response.send_message("❌ ไอเทมไม่พอ", ephemeral=True)

            if res[0] == amount: await db.execute("DELETE FROM inventory WHERE user_id=? AND item_name=?", (interaction.user.id, item_name))
            else: await db.execute("UPDATE inventory SET amount=amount-? WHERE user_id=? AND item_name=?", (amount, interaction.user.id, item_name))

            async with db.execute("SELECT amount FROM inventory WHERE user_id=? AND item_name=?", (recipient.id, item_name)) as c:
                has = await c.fetchone()
            if has: await db.execute("UPDATE inventory SET amount=amount+? WHERE user_id=? AND item_name=?", (amount, recipient.id, item_name))
            else: await db.execute("INSERT INTO inventory (user_id, item_name, amount) VALUES (?,?,?)", (recipient.id, item_name, amount))
            
            await db.commit()
        
        await interaction.response.send_message(f"🎁 ส่ง **{item_name}** x{amount} ให้ {recipient.mention} แล้ว", ephemeral=False)

class InventoryView(discord.ui.View):
    def __init__(self, items):
        super().__init__()
        self.add_item(InventorySelect(items))

class InventorySelect(discord.ui.Select):
    def __init__(self, items):
        options = []
        for n, a, d, i in items[:25]:
            options.append(discord.SelectOption(label=f"{n} (x{a})", value=n))
        super().__init__(placeholder="ดูรายละเอียด...", options=options)

    async def callback(self, interaction):
        name = self.values[0]
        # (In real app, pass items dict to avoid requery, simplified here)
        # Assuming item details in self.view or fetched again. 
        # For simplicity, just acknowledge.
        await interaction.response.send_message(f"📦 {name}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Inventory(bot))
