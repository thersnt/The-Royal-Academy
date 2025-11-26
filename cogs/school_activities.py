import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import os
import datetime
import random
import asyncio
from utils import load_data, PROFILE_FILE 

DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"
SYSTEM_ID = 0 

WEEKLY_LIMIT = 2
WISH_COST = 10
TEA_HOST_COST = 0 # จัดฟรี
TEA_REWARD_HOST = 50
TEA_REWARD_GUEST = 20

STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"]

POTION_INGREDIENTS = [
    {"label": "น้ำค้างรุ่งอรุณ (Morning Dew)", "value": "dew", "price": 5, "emoji": "💧"},
    {"label": "หางจิ้งจกตากแห้ง (Dried Lizard Tail)", "value": "lizard", "price": 15, "emoji": "🦎"},
    {"label": "ตาแมงมุมหมัก (Spider Eye)", "value": "spider_eye", "price": 30, "emoji": "🕷️"},
    {"label": "ปีกค้างคาวตากแห้ง (Bat Wing)", "value": "bat_wing", "price": 50, "emoji": "🦇"},
    {"label": "ยางไม้เอนท์ (Ent Sap)", "value": "ent_sap", "price": 80, "emoji": "🌳"},
    {"label": "รากแมนดราโกรา (Mandrake Root)", "value": "mandrake", "price": 120, "emoji": "🌱"},
    {"label": "ขนหางยูนิคอร์น (Unicorn Hair)", "value": "unicorn", "price": 180, "emoji": "🦄"},
    {"label": "เกล็ดมังกรไฟ (Dragon Scale)", "value": "dragon", "price": 250, "emoji": "🐉"},
    {"label": "ผงมูนสโตน (Moonstone Dust)", "value": "moonstone", "price": 350, "emoji": "🌑"},
    {"label": "ขนนกฟีนิกซ์ (Phoenix Feather)", "value": "phoenix", "price": 500, "emoji": "🔥"}
]

class SchoolActivities(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def cog_load(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    activity_type TEXT,
                    timestamp TEXT
                )
            """)
            await db.commit()

    def _get_week_start(self):
        today = datetime.datetime.utcnow()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    async def _check_weekly_limit(self, user_id: int, activity_type: str) -> bool:
        week_start = self._get_week_start()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM activity_logs WHERE user_id = ? AND activity_type = ? AND timestamp >= ?", 
                                  (user_id, activity_type, week_start)) as cursor:
                count = (await cursor.fetchone())[0]
        return count < WEEKLY_LIMIT

    async def _log_activity(self, user_id: int, activity_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO activity_logs (user_id, activity_type, timestamp) VALUES (?, ?, ?)", 
                             (user_id, activity_type, datetime.datetime.utcnow().isoformat()))
            await db.commit()

    async def _get_remaining_quota(self, user_id: int, activity_type: str) -> int:
        week_start = self._get_week_start()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM activity_logs WHERE user_id = ? AND activity_type = ? AND timestamp >= ?", 
                                  (user_id, activity_type, week_start)) as cursor:
                count = (await cursor.fetchone())[0]
        return max(0, WEEKLY_LIMIT - count)

    async def _remove_last_activity_log(self, user_id: int, activity_type: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                DELETE FROM activity_logs 
                WHERE id = (
                    SELECT id FROM activity_logs 
                    WHERE user_id = ? AND activity_type = ? 
                    ORDER BY timestamp DESC LIMIT 1
                )
            """, (user_id, activity_type))
            await db.commit()

    async def _notify_wallet_thread(self, target_member, embed):
        try:
            profiles = load_data(PROFILE_FILE)
            wallet_id = profiles.get(str(target_member.id), {}).get('wallet_thread_id')
            if wallet_id:
                channel = self.bot.get_channel(int(wallet_id))
                if channel: await channel.send(embed=embed)
        except: pass

    async def _process_transaction(self, user_id: int, amount: int, tx_type: str, is_income: bool):
        async with aiosqlite.connect(self.db_path) as db:
            timestamp = datetime.datetime.utcnow().isoformat()
            if is_income:
                await db.execute("UPDATE royals SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                await db.execute("INSERT INTO transactions (timestamp, type, source_id, target_id, amount) VALUES (?, ?, ?, ?, ?)", (timestamp, tx_type, SYSTEM_ID, user_id, amount))
            else:
                await db.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                await db.execute("INSERT INTO transactions (timestamp, type, source_id, target_id, amount) VALUES (?, ?, ?, ?, ?)", (timestamp, tx_type, user_id, SYSTEM_ID, amount))
            await db.commit()
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (user_id,)) as cursor:
                new_bal = (await cursor.fetchone())[0]
        return new_bal

    @app_commands.command(name="reset_activity_limit", description="[STAFF] รีเซ็ตโควตากิจกรรมของสมาชิก")
    async def reset_activity_limit(self, interaction: discord.Interaction, member: discord.Member, activity: str = None):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        async with aiosqlite.connect(self.db_path) as db:
            if activity:
                await db.execute("DELETE FROM activity_logs WHERE user_id = ? AND activity_type = ?", (member.id, activity))
                msg = f"✅ รีเซ็ตโควตา **{activity}** ของ {member.mention} เรียบร้อยแล้ว"
            else:
                await db.execute("DELETE FROM activity_logs WHERE user_id = ?", (member.id,))
                msg = f"✅ รีเซ็ตโควตา **ทุกกิจกรรม** ของ {member.mention} เรียบร้อยแล้ว"
            await db.commit()
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="wish", description="โยนเหรียญ 10 R ลงบ่อ (จำกัด 2 ครั้ง/สัปดาห์)")
    async def wish(self, interaction: discord.Interaction):
        if not await self._check_weekly_limit(interaction.user.id, "wish"):
            return await interaction.response.send_message("❌ คุณใช้โควตา 'ขอพร' ครบ 2 ครั้งในสัปดาห์นี้แล้ว", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)) as cursor:
                res = await cursor.fetchone()
                balance = res[0] if res else 0
        
        if balance < WISH_COST: 
            return await interaction.response.send_message(f"❌ เงินไม่พอ (ต้องการ {WISH_COST} {CURRENCY_SYMBOL})", ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        await self._process_transaction(interaction.user.id, WISH_COST, "LUCK_WISH_TOSS", False)
        await interaction.followup.send(f"🪙 **{interaction.user.display_name}** โยนเหรียญ {WISH_COST} {CURRENCY_SYMBOL} ลงบ่อน้ำ...\n*จ๋อม!*")
        await asyncio.sleep(2)

        rand_val = random.random() * 100
        multiplier = 0
        if rand_val <= 50: multiplier = 0
        elif rand_val <= 80: multiplier = 1
        elif rand_val <= 93: multiplier = 2
        elif rand_val <= 98: multiplier = 3
        else: multiplier = 4

        prize = WISH_COST * multiplier
        embed = discord.Embed(title="⛲ ผลคำอธิษฐาน", color=discord.Color.blue())
        new_bal = 0

        if multiplier == 0:
            embed.description = "เหรียญจมหายไปในความมืด... ไม่มีอะไรเกิดขึ้น\n💸 **เสียเงินฟรี**"
            embed.color = discord.Color.dark_grey()
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)) as cursor:
                    new_bal = (await cursor.fetchone())[0]
        else:
            new_bal = await self._process_transaction(interaction.user.id, prize, "LUCK_WISH_GRANT", True)
            desc_text = "รู้สึกจิตใจสงบ... เทพธิดาคืนเหรียญให้คุณ" if multiplier == 1 else \
                        "ผิวน้ำส่องแสงระยิบระยับ! คำอธิษฐานเป็นจริงเล็กน้อย" if multiplier == 2 else \
                        "น้ำพุพุ่งสูงขึ้นฟ้า! คำอธิษฐานของคุณแรงกล้ามาก" if multiplier == 3 else \
                        "🌈 **ปาฏิหาริย์!** เทพธิดาแห่งบ่อน้ำปรากฏตัว!"
            if multiplier == 4: 
                embed.color = discord.Color.purple()
                embed.set_image(url="https://iili.io/f3RX0e1.png")
            elif multiplier == 1: embed.color = discord.Color.light_grey()
            elif multiplier == 2: embed.color = discord.Color.green()
            elif multiplier == 3: embed.color = discord.Color.gold()
            embed.description = f"{desc_text}\n✨ **ได้รับคืน:** `{prize} {CURRENCY_SYMBOL}` (x{multiplier})"

        await self._log_activity(interaction.user.id, "wish")
        rem = await self._get_remaining_quota(interaction.user.id, "wish")
        embed.set_footer(text=f"โควตาขอพรคงเหลือ: {rem}/2 | ยอดเงิน: {new_bal:,} {CURRENCY_SYMBOL}")
        
        msg = await interaction.original_response()
        await msg.edit(content=None, embed=embed)
        
        receipt = discord.Embed(title="🧾 บันทึกกิจกรรม: บ่อน้ำศักดิ์สิทธิ์", color=embed.color, timestamp=datetime.datetime.now())
        receipt.add_field(name="จ่าย", value=f"{WISH_COST} {CURRENCY_SYMBOL}", inline=True)
        receipt.add_field(name="ได้รับ", value=f"{prize} {CURRENCY_SYMBOL}", inline=True)
        receipt.add_field(name="คงเหลือ", value=f"{new_bal:,} {CURRENCY_SYMBOL}", inline=True)
        await self._notify_wallet_thread(interaction.user, receipt)

    @app_commands.command(name="brew_potion", description="เลือกส่วนผสมเพื่อปรุงยา (จำกัด 2 ครั้ง/สัปดาห์)")
    async def brew_potion(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._check_weekly_limit(interaction.user.id, "brew_potion"):
            return await interaction.followup.send("❌ คุณใช้โควตา 'ปรุงยา' ครบ 2 ครั้งในสัปดาห์นี้แล้ว", ephemeral=True)

        view = PotionBrewingView(interaction.user, self)
        embed = discord.Embed(title="⚗️ ห้องปรุงยา", description="เลือก **อย่างน้อย 3 ส่วนผสม** เพื่อเริ่มการทดลอง\n\n💰 **กฎการปรุงยา:**\n• เงินจะถูกหักทันทีเมื่อเริ่มปรุง\n• ยิ่งใช้วัตถุดิบราคาสูง โอกาสสำเร็จยิ่งมาก!", color=discord.Color.dark_purple())
        price_list = "\n".join([f"{i['emoji']} {i['label']}: **{i['price']} R**" for i in POTION_INGREDIENTS])
        embed.add_field(name="📜 รายการวัตถุดิบ", value=price_list)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="host_teaparty", description="จัดปาร์ตี้น้ำชา (จัดได้ 2 ครั้ง/สัปดาห์)")
    async def host_teaparty(self, interaction: discord.Interaction, theme: str = "จิบชายามบ่าย", max_participants: int = 6):
        if not (2 <= max_participants <= 10): 
            return await interaction.response.send_message("❌ จำนวนคนต้องอยู่ระหว่าง 2 - 10 คน", ephemeral=True)
        
        if not await self._check_weekly_limit(interaction.user.id, "host_teaparty"): 
            return await interaction.response.send_message("❌ คุณใช้โควตา 'จัดปาร์ตี้' ครบแล้ว", ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        await self._process_transaction(interaction.user.id, TEA_HOST_COST, "TEA_PARTY_HOST", False)
        await self._log_activity(interaction.user.id, "host_teaparty")

        view = TeaPartyLobbyView(interaction.user, theme, max_participants, self)
        embed = discord.Embed(title=f"☕ Tea Party: {theme}", description=f"**{interaction.user.display_name}** เปิดโต๊ะน้ำชา!\nต้องการสมาชิก: **{max_participants} คน**\n\n*เมื่อคนครบแล้ว เจ้าภาพกดเริ่มเพื่อเข้าสู่ช่วงโรลเพลย์*", color=discord.Color.from_rgb(255, 182, 193))
        embed.add_field(name="ผู้เข้าร่วม", value=f"1. {interaction.user.mention} (Host)", inline=False)
        
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

# --- Views ---

class PotionIngredientSelect(discord.ui.Select):
    def __init__(self, selected_values=None):
        options = []
        if selected_values is None: selected_values = []
        
        # ✅ FIX: บังคับแปลงค่า selected_values เป็น string ทั้งหมด
        safe_selected = [str(v) for v in selected_values]

        for i in POTION_INGREDIENTS:
            val_str = str(i['value'])
            # ✅ FIX: บังคับแปลงผลลัพธ์เป็น bool (True/False) ชัดเจน (แก้ Invalid Form Body)
            is_default = bool(val_str in safe_selected)
            
            options.append(discord.SelectOption(
                label=i['label'], 
                value=val_str, 
                emoji=i['emoji'], 
                description=f"ราคา: {i['price']} {CURRENCY_SYMBOL}", 
                default=is_default
            ))
            
        super().__init__(placeholder="เลือกส่วนผสม...", min_values=1, max_values=len(POTION_INGREDIENTS), options=options)

    async def callback(self, interaction):
        self.view.selected_ingredients = self.values
        await self.view.update_embed(interaction)

class PotionBrewingView(discord.ui.View):
    def __init__(self, user, cog):
        super().__init__(timeout=300)
        self.user = user
        self.cog = cog
        self.selected_ingredients = []
        self._update_components()

    def _update_components(self):
        self.clear_items()
        self.add_item(PotionIngredientSelect(self.selected_ingredients))
        disabled = len(self.selected_ingredients) < 3
        
        # ✅ แก้ไข Signature ของ callback ให้ถูกต้อง
        start_btn = discord.ui.Button(label="🔥 เริ่มปรุงยา", style=discord.ButtonStyle.danger, disabled=disabled)
        start_btn.callback = self.start_brew
        self.add_item(start_btn)

    def get_total_cost(self):
        total = 0
        for val in self.selected_ingredients:
            for i in POTION_INGREDIENTS:
                if str(i['value']) == str(val): total += i['price']
        return total

    async def update_embed(self, interaction):
        total_cost = self.get_total_cost()
        embed = interaction.message.embeds[0]
        embed.clear_fields()
        
        price_list = "\n".join([f"{i['emoji']} {i['label']}: **{i['price']} R**" for i in POTION_INGREDIENTS])
        embed.add_field(name="📜 รายการวัตถุดิบ", value=price_list, inline=False)
        
        selected = [f"{i['emoji']} {i['label']}" for val in self.selected_ingredients for i in POTION_INGREDIENTS if str(i['value']) == str(val)]
        embed.add_field(name="เลือกแล้ว", value="\n".join(selected) if selected else "-", inline=False)
        embed.add_field(name="รวม", value=f"**{total_cost:,} R**", inline=False)
        
        self._update_components()
        await interaction.response.edit_message(embed=embed, view=self)

    async def start_brew(self, interaction):
        if interaction.user.id != self.user.id: 
            return await interaction.response.send_message("คุณไม่ใช่เจ้าของหม้อปรุงยานี้", ephemeral=True)
        
        total_cost = self.get_total_cost()
        
        async with aiosqlite.connect(self.cog.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,)) as c:
                res = await c.fetchone()
                bal = res[0] if res else 0
        
        if bal < total_cost: return await interaction.response.send_message("❌ เงินไม่พอ", ephemeral=True)

        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

        new_bal = await self.cog._process_transaction(interaction.user.id, total_cost, "LUCK_BREW_COST", False)
        
        receipt = discord.Embed(title="🧾 จ่ายค่าปรุงยา", color=discord.Color.red())
        receipt.add_field(name="จ่าย", value=f"-{total_cost}")
        receipt.add_field(name="เหลือ", value=f"{new_bal}")
        await self.cog._notify_wallet_thread(interaction.user, receipt)

        await interaction.followup.send("🔥 เริ่มปรุงยา...")
        await asyncio.sleep(3)

        scale = min(total_cost / 1000, 1.0)
        if total_cost < 100: w = [15, 50, 25, 9, 1]
        elif total_cost < 300: w = [10, 30, 40, 18, 2]
        elif total_cost < 600: w = [8, 15, 35, 35, 7]
        else: w = [5, 5, 20, 45, 25]
        
        res_type = random.choices(["Fail", "Low", "Medium", "Good", "Excellent"], weights=w)[0]
        
        bonus = 0
        reward = 0
        title, desc, color = "", "", discord.Color.default()
        
        if res_type == "Fail":
            title, desc, color = "💥 หม้อระเบิด!", "ล้มเหลว! ไม่ได้เงินคืน", discord.Color.dark_red()
        else:
            if res_type == "Low": 
                bonus = int(10 + 10*scale)
                title, desc, color = "🧪 คุณภาพต่ำ", f"คืนทุน + กำไร {bonus} R", discord.Color.light_grey()
            elif res_type == "Medium": 
                bonus = int(30 + 20*scale)
                title, desc, color = "⚗️ คุณภาพปานกลาง", f"คืนทุน + กำไร {bonus} R", discord.Color.blue()
            elif res_type == "Good": 
                bonus = int(40 + 50*scale)
                title, desc, color = "✨ คุณภาพดี", f"คืนทุน + กำไร {bonus} R", discord.Color.gold()
            elif res_type == "Excellent": 
                bonus = int(100 + 100*scale)
                title, desc, color = "👑 คุณภาพยอดเยี่ยม", f"คืนทุน + กำไร {bonus} R", discord.Color.purple()
            reward = total_cost + bonus
        
        await self.cog._log_activity(interaction.user.id, "brew_potion")
        
        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name="ลงทุน", value=f"{total_cost}")
        
        if reward > 0:
            nb = await self.cog._process_transaction(interaction.user.id, reward, "LUCK_BREW_SOLD", True)
            embed.add_field(name="ขายได้", value=f"+{reward}")
            
            rec = discord.Embed(title="💰 ขายน้ำยา", color=discord.Color.green())
            rec.add_field(name="ระดับ", value=res_type)
            rec.add_field(name="ได้รับ", value=f"+{reward}")
            rec.add_field(name="เหลือ", value=f"{nb}")
            await self.cog._notify_wallet_thread(interaction.user, rec)
        else:
            embed.add_field(name="ผล", value="สูญเสียทั้งหมด")

        rem = await self.cog._get_remaining_quota(interaction.user.id, "brew_potion")
        embed.set_footer(text=f"โควตาเหลือ: {rem}/2")
        await interaction.edit_original_response(content=None, embed=embed)

class TeaPartyTopicModal(discord.ui.Modal, title='หัวข้อโรลเพลย์'):
    def __init__(self, participants, cog, theme, msg, host):
        super().__init__()
        self.participants = participants
        self.cog = cog
        self.theme = theme
        self.msg = msg
        self.host = host
        self.t1 = discord.ui.TextInput(label='Topic 1', default='แนะนำตัวและรินน้ำชา', required=True)
        self.t2 = discord.ui.TextInput(label='Topic 2', default='ลิ้มรสขนมหวาน', required=True)
        self.t3 = discord.ui.TextInput(label='Topic 3', default='เรื่องราวในโรงเรียน', required=True)
        self.add_item(self.t1); self.add_item(self.t2); self.add_item(self.t3)

    async def on_submit(self, interaction):
        await interaction.response.defer()
        try:
            embed = self.msg.embeds[0]
            embed.description += "\n\n✅ **งานเริ่มแล้ว!**"
            embed.color = discord.Color.green()
            await self.msg.edit(embed=embed, view=None)
        except: pass
        topics = [self.t1.value, self.t2.value, self.t3.value]
        rp = TeaPartyRoleplayView(self.participants, interaction.channel, self.cog, self.theme, topics, self.host)
        await rp.start_round(interaction.channel)

class TeaPartyLobbyView(discord.ui.View):
    def __init__(self, host, theme, max_p, cog):
        super().__init__(timeout=300)
        self.host = host
        self.theme = theme
        self.max_p = max_p
        self.cog = cog
        self.participants = [host]
        self.message = None

    @discord.ui.button(label="Join", style=discord.ButtonStyle.green)
    async def join(self, interaction, button):
        if interaction.user in self.participants: return await interaction.response.send_message("Already joined", ephemeral=True)
        self.participants.append(interaction.user)
        embed = interaction.message.embeds[0]
        names = [f"{i+1}. {p.mention} {'(Host)' if p==self.host else ''}" for i, p in enumerate(self.participants)]
        embed.set_field_at(0, name="รายชื่อ", value="\n".join(names), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start(self, interaction, button):
        if interaction.user != self.host: return
        await interaction.response.send_modal(TeaPartyTopicModal(self.participants, self.cog, self.theme, self.message, self.host))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        if interaction.user != self.host: return
        await self.cog._remove_last_activity_log(self.host.id, "host_teaparty")
        await interaction.response.edit_message(content="Cancelled", view=None, embed=None)

class TeaPartyRoleplayView(discord.ui.View):
    def __init__(self, participants, channel, cog, theme, topics, host):
        super().__init__(timeout=1200)
        self.participants = participants
        self.channel = channel
        self.cog = cog
        self.topics = topics
        self.host = host
        self.round = 0
        self.done = set()
        self.start_time = None
        self.msg = None
        self.processing = set()
        self.transitioning = False

    async def start_round(self, channel):
        if self.msg:
            try:
                embed = self.msg.embeds[0]
                embed.set_footer(text="รอบนี้จบแล้ว")
                await self.msg.edit(view=None, embed=embed)
            except: pass

        self.round += 1
        self.done.clear()
        self.start_time = discord.utils.utcnow()
        embed = discord.Embed(title=f"☕ Round {self.round}/3", description=f"**หัวข้อ:** {self.topics[self.round-1]}\n\nพิมพ์ RP แล้วกดปุ่มส่ง", color=discord.Color.gold())
        self.msg = await channel.send(embed=embed, view=self)
        self.transitioning = False

    async def _verify(self, user):
        async for m in self.channel.history(limit=20):
            if m.author.id == user.id and m.created_at >= self.start_time: return True
        return False

    @discord.ui.button(label="Submit RP", style=discord.ButtonStyle.success)
    async def submit(self, interaction, button):
        if interaction.user not in self.participants: return
        if interaction.user.id in self.processing: return
        self.processing.add(interaction.user.id)
        
        if await self._verify(interaction.user):
            self.done.add(interaction.user.id)
            embed = interaction.message.embeds[0]
            lines = [f"{p.mention}: {'✅' if p.id in self.done else '⏳'}" for p in self.participants]
            embed.clear_fields()
            embed.add_field(name="Status", value="\n".join(lines))
            await interaction.response.edit_message(embed=embed)
            
            if len(self.done) == len(self.participants):
                if self.transitioning: return
                self.transitioning = True
                if self.round < 3: await self.start_round(self.channel)
                else: await self.finish()
        else:
            await interaction.response.send_message("ไม่พบข้อความ RP", ephemeral=True)
        self.processing.remove(interaction.user.id)

    async def finish(self):
        if self.msg: await self.msg.edit(view=None)
        await self.channel.send(embed=discord.Embed(title="🎉 ปาร์ตี้จบลงแล้ว!", description="ขอบคุณทุกคนที่มาร่วมงาน", color=discord.Color.purple()))
        for p in self.participants:
            amt = TEA_REWARD_HOST if p.id == self.host.id else TEA_REWARD_GUEST
            nb = await self.cog._process_transaction(p.id, amt, "TEA_PARTY", True)
            rec = discord.Embed(title="Tea Party Reward", description=f"+{amt} R\nBal: {nb}", color=discord.Color.from_rgb(255, 182, 193))
            await self.cog._notify_wallet_thread(p, rec)

async def setup(bot):
    await bot.add_cog(SchoolActivities(bot))


