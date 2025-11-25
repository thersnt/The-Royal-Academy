import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
import datetime
import random
import asyncio
from utils import load_data, PROFILE_FILE 

# --- ⚙️ ตั้งค่าระบบกิจกรรม ---
DB_NAME = 'school_data.db'
CURRENCY_SYMBOL = "R"
SYSTEM_ID = 0 

# Limits
WEEKLY_LIMIT = 2        # โควตาต่อกิจกรรม
WISH_COST = 10          # ค่าโยนเหรียญ (Fixed 10 R)
TEA_HOST_COST = 0       # [UPDATED] ค่าจัดปาร์ตี้เป็น 0 (ฟรี)

# Rewards
TEA_REWARD_HOST = 50    # รางวัลเจ้าภาพ
TEA_REWARD_GUEST = 20   # รางวัลผู้เข้าร่วม

STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"]

# 🧪 รายชื่อส่วนผสมปรุงยา
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
        self._create_tables()

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def _create_tables(self):
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                activity_type TEXT,
                timestamp TEXT
            )
        """)
        conn.commit()
        conn.close()

    # --- Helpers ---
    def _get_week_start(self):
        today = datetime.datetime.utcnow()
        start_of_week = today - datetime.timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_of_week.isoformat()

    def _check_weekly_limit(self, user_id: int, activity_type: str) -> bool:
        week_start = self._get_week_start()
        conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM activity_logs WHERE user_id = ? AND activity_type = ? AND timestamp >= ?", 
                           (user_id, activity_type, week_start))
            count = cursor.fetchone()[0]
            return count < WEEKLY_LIMIT
        finally:
            conn.close()

    def _log_activity(self, user_id: int, activity_type: str):
        conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO activity_logs (user_id, activity_type, timestamp) VALUES (?, ?, ?)", 
                           (user_id, activity_type, datetime.datetime.utcnow().isoformat()))
            conn.commit()
        finally:
            conn.close()

    def _get_remaining_quota(self, user_id: int, activity_type: str) -> int:
        week_start = self._get_week_start()
        conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM activity_logs WHERE user_id = ? AND activity_type = ? AND timestamp >= ?", 
                           (user_id, activity_type, week_start))
            count = cursor.fetchone()[0]
            return max(0, WEEKLY_LIMIT - count)
        finally:
            conn.close()

    def _remove_last_activity_log(self, user_id: int, activity_type: str):
        conn = self._get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM activity_logs 
                WHERE id = (
                    SELECT id FROM activity_logs 
                    WHERE user_id = ? AND activity_type = ? 
                    ORDER BY timestamp DESC LIMIT 1
                )
            """, (user_id, activity_type))
            conn.commit()
        finally:
            conn.close()

    async def _notify_wallet_thread(self, target_member: discord.Member, embed: discord.Embed):
        sent_to_thread = False
        try:
            profiles = load_data(PROFILE_FILE)
            user_id_str = str(target_member.id)
            wallet_thread_id = profiles.get(user_id_str, {}).get('wallet_thread_id')
            if wallet_thread_id:
                wallet_thread = self.bot.get_channel(int(wallet_thread_id))
                if wallet_thread: 
                    await wallet_thread.send(embed=embed)
                    sent_to_thread = True
        except: pass
        if not sent_to_thread:
            try: await target_member.send(embed=embed)
            except: pass

    def _process_transaction(self, user_id: int, amount: int, tx_type: str, is_income: bool):
        conn = self._get_db()
        cursor = conn.cursor()
        try:
            timestamp = datetime.datetime.utcnow().isoformat()
            if is_income:
                cursor.execute("UPDATE royals SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                cursor.execute("INSERT INTO transactions (timestamp, type, source_id, target_id, amount) VALUES (?, ?, ?, ?, ?)", (timestamp, tx_type, SYSTEM_ID, user_id, amount))
            else:
                cursor.execute("UPDATE royals SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                cursor.execute("INSERT INTO transactions (timestamp, type, source_id, target_id, amount) VALUES (?, ?, ?, ?, ?)", (timestamp, tx_type, user_id, SYSTEM_ID, amount))
            conn.commit()
            cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (user_id,))
            return cursor.fetchone()[0]
        except: return 0
        finally: conn.close()

    # --- 🛠️ Admin Commands ---
    @app_commands.command(name="reset_activity_limit", description="[STAFF] รีเซ็ตโควตากิจกรรมของสมาชิก")
    @app_commands.describe(member="สมาชิกที่ต้องการรีเซ็ต", activity="เลือกกิจกรรมที่จะรีเซ็ต (ไม่เลือก = รีเซ็ตทั้งหมด)")
    @app_commands.choices(activity=[
        app_commands.Choice(name="⛲ บ่อน้ำศักดิ์สิทธิ์ (Wish)", value="wish"),
        app_commands.Choice(name="⚗️ ปรุงยา (Brew Potion)", value="brew_potion"),
        app_commands.Choice(name="☕ จัดปาร์ตี้น้ำชา (Host Tea Party)", value="host_teaparty")
    ])
    async def reset_activity_limit(self, interaction: discord.Interaction, member: discord.Member, activity: app_commands.Choice[str] = None):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        conn = self._get_db()
        try:
            cursor = conn.cursor()
            if activity:
                # รีเซ็ตเฉพาะกิจกรรมที่เลือก
                cursor.execute("DELETE FROM activity_logs WHERE user_id = ? AND activity_type = ?", (member.id, activity.value))
                msg = f"✅ รีเซ็ตโควตา **{activity.name}** ของ {member.mention} เรียบร้อยแล้ว"
            else:
                # รีเซ็ตทั้งหมด
                cursor.execute("DELETE FROM activity_logs WHERE user_id = ?", (member.id,))
                msg = f"✅ รีเซ็ตโควตา **ทุกกิจกรรม** ของ {member.mention} เรียบร้อยแล้ว"
            
            conn.commit()
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            print(f"Reset Error: {e}")
            await interaction.followup.send("❌ เกิดข้อผิดพลาดในการรีเซ็ต", ephemeral=True)
        finally: conn.close()

    # ⛲ Wish
    @app_commands.command(name="wish", description="โยนเหรียญ 10 R ลงบ่อ (จำกัด 2 ครั้ง/สัปดาห์)")
    async def wish(self, interaction: discord.Interaction):
        activity_name = "wish"
        amount = WISH_COST 
        
        if not self._check_weekly_limit(interaction.user.id, activity_name):
            return await interaction.response.send_message("❌ คุณใช้โควตา 'ขอพร' ครบ 2 ครั้งในสัปดาห์นี้แล้ว", ephemeral=True)

        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,))
        res = cursor.fetchone()
        balance = res[0] if res else 0
        conn.close()
        
        if balance < amount: 
            return await interaction.response.send_message(f"❌ เงินไม่พอ (ต้องการ {amount} {CURRENCY_SYMBOL})", ephemeral=True)

        await interaction.response.defer(ephemeral=False)

        self._process_transaction(interaction.user.id, amount, "LUCK_WISH_TOSS", False)
        await interaction.followup.send(f"🪙 **{interaction.user.display_name}** โยนเหรียญ {amount} {CURRENCY_SYMBOL} ลงบ่อน้ำ...\n*จ๋อม!*")
        await asyncio.sleep(2)

        rand_val = random.random() * 100
        multiplier = 0
        if rand_val <= 50: multiplier = 0
        elif rand_val <= 80: multiplier = 1
        elif rand_val <= 93: multiplier = 2
        elif rand_val <= 98: multiplier = 3
        else: multiplier = 4

        prize = amount * multiplier
        outcome_embed = discord.Embed(title="⛲ ผลคำอธิษฐาน", color=discord.Color.blue())
        new_balance = 0

        if multiplier == 0:
            outcome_embed.description = "เหรียญจมหายไปในความมืด... ไม่มีอะไรเกิดขึ้น\n💸 **เสียเงินฟรี**"
            outcome_embed.color = discord.Color.dark_grey()
            conn = self._get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,))
            new_balance = cursor.fetchone()[0]
            conn.close()
        else:
            new_balance = self._process_transaction(interaction.user.id, prize, "LUCK_WISH_GRANT", True)
            
            desc_text = ""
            if multiplier == 1:
                desc_text = "รู้สึกจิตใจสงบ... เทพธิดาคืนเหรียญให้คุณ"
                outcome_embed.color = discord.Color.light_grey()
            elif multiplier == 2:
                desc_text = "ผิวน้ำส่องแสงระยิบระยับ! คำอธิษฐานเป็นจริงเล็กน้อย"
                outcome_embed.color = discord.Color.green()
            elif multiplier == 3:
                desc_text = "น้ำพุพุ่งสูงขึ้นฟ้า! คำอธิษฐานของคุณแรงกล้ามาก"
                outcome_embed.color = discord.Color.gold()
            elif multiplier == 4:
                desc_text = "🌈 **ปาฏิหาริย์!** เทพธิดาแห่งบ่อน้ำปรากฏตัว!"
                outcome_embed.color = discord.Color.purple()
                outcome_embed.set_image(url="https://iili.io/f3RX0e1.png")

            outcome_embed.description = f"{desc_text}\n✨ **ได้รับคืน:** `{prize} {CURRENCY_SYMBOL}` (x{multiplier})"

        self._log_activity(interaction.user.id, activity_name)
        remaining = self._get_remaining_quota(interaction.user.id, activity_name)
        outcome_embed.set_footer(text=f"โควตาขอพรคงเหลือ: {remaining}/2 | ยอดเงิน: {new_balance:,} {CURRENCY_SYMBOL}")
        
        msg = await interaction.original_response()
        await msg.edit(content=None, embed=outcome_embed)
        
        receipt = discord.Embed(title="🧾 บันทึกกิจกรรม: บ่อน้ำศักดิ์สิทธิ์", color=outcome_embed.color, timestamp=datetime.datetime.now())
        receipt.add_field(name="จ่าย", value=f"{amount} {CURRENCY_SYMBOL}", inline=True)
        receipt.add_field(name="ได้รับ", value=f"{prize} {CURRENCY_SYMBOL}", inline=True)
        receipt.add_field(name="คงเหลือ", value=f"{new_balance:,} {CURRENCY_SYMBOL}", inline=True)
        await self._notify_wallet_thread(interaction.user, receipt)

    # ⚗️ Brew Potion
    @app_commands.command(name="brew_potion", description="เลือกส่วนผสมเพื่อปรุงยา (จำกัด 2 ครั้ง/สัปดาห์)")
    async def brew_potion(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) 
        activity_name = "brew_potion"
        if not self._check_weekly_limit(interaction.user.id, activity_name):
            return await interaction.followup.send("❌ คุณใช้โควตา 'ปรุงยา' ครบ 2 ครั้งในสัปดาห์นี้แล้ว", ephemeral=True)

        view = PotionBrewingView(interaction.user, self)
        embed = discord.Embed(title="⚗️ ห้องปรุงยา", description="เลือก **อย่างน้อย 3 ส่วนผสม** เพื่อเริ่มการทดลอง\n\n💰 **กฎการปรุงยา:**\n• เงินจะถูกหักทันทีเมื่อเริ่มปรุง\n• ยิ่งใช้วัตถุดิบราคาสูง โอกาสสำเร็จยิ่งมาก!", color=discord.Color.dark_purple())
        price_list = ""
        for i in POTION_INGREDIENTS:
            price_list += f"{i['emoji']} {i['label']}: **{i['price']} R**\n"
        embed.add_field(name="📜 รายการวัตถุดิบ", value=price_list)
        await interaction.followup.send(embed=embed, view=view)

    # ☕ Tea Party
    @app_commands.command(name="host_teaparty", description="จัดปาร์ตี้น้ำชา (จัดได้ 2 ครั้ง/สัปดาห์, จัดฟรี)")
    @app_commands.describe(theme="ธีมงาน", max_participants="จำนวนคน (2-10)")
    async def host_teaparty(self, interaction: discord.Interaction, theme: str = "จิบชายามบ่าย", max_participants: int = 6):
        activity_name = "host_teaparty"
        
        # Check Logic
        if not (2 <= max_participants <= 10): 
            return await interaction.response.send_message("❌ จำนวนคนต้องอยู่ระหว่าง 2 - 10 คน", ephemeral=True)
        
        if not self._check_weekly_limit(interaction.user.id, activity_name): 
            return await interaction.response.send_message("❌ คุณใช้โควตา 'จัดปาร์ตี้' ครบแล้ว", ephemeral=True)

        # [UPDATED] ไม่ต้องเช็คเงินและไม่ต้องหักเงิน เพราะฟรี
        await interaction.response.defer(ephemeral=False)

        # Log Activity ทันที (นับโควตา)
        self._log_activity(interaction.user.id, activity_name)

        view = TeaPartyLobbyView(interaction.user, theme, max_participants, self)
        embed = discord.Embed(title=f"☕ Tea Party: {theme}", description=f"**{interaction.user.display_name}** เปิดโต๊ะน้ำชา!\nต้องการสมาชิก: **{max_participants} คน**\n\n*เมื่อคนครบแล้ว เจ้าภาพกดเริ่มเพื่อเข้าสู่ช่วงโรลเพลย์*", color=discord.Color.from_rgb(255, 182, 193))
        embed.add_field(name="ผู้เข้าร่วม", value=f"1. {interaction.user.mention} (Host)", inline=False)
        embed.set_footer(text="ค่าจัดงาน: ฟรี | โควตาจัด: 2 ครั้ง/สัปดาห์")
        
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message

# --- ⚗️ Potion Classes ---
class PotionIngredientSelect(discord.ui.Select):
    def __init__(self, selected_values=None):
        options = []
        if selected_values is None: selected_values = []
        for i in POTION_INGREDIENTS:
            is_default = i['value'] in selected_values
            options.append(discord.SelectOption(label=i['label'], value=i['value'], emoji=i['emoji'], description=f"ราคา: {i['price']} {CURRENCY_SYMBOL}", default=is_default))
        super().__init__(placeholder="เลือกส่วนผสม (อย่างน้อย 3 ชนิด)...", min_values=1, max_values=len(POTION_INGREDIENTS), options=options)

    async def callback(self, interaction: discord.Interaction):
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
        start_btn = discord.ui.Button(label="🔥 เริ่มปรุงยา", style=discord.ButtonStyle.danger, disabled=disabled, custom_id="start_brew_btn")
        start_btn.callback = self.start_brew 
        self.add_item(start_btn)

    def get_total_cost(self):
        total = 0
        for val in self.selected_ingredients:
            for item in POTION_INGREDIENTS:
                if item['value'] == val: total += item['price']
        return total

    async def update_embed(self, interaction: discord.Interaction):
        total_cost = self.get_total_cost()
        if interaction.message:
            embed = interaction.message.embeds[0]
            embed.clear_fields()
            price_list = ""
            for i in POTION_INGREDIENTS: price_list += f"{i['emoji']} {i['label']}: **{i['price']} R**\n"
            embed.add_field(name="📜 รายการวัตถุดิบ", value=price_list, inline=False)
            selected_names = []
            for val in self.selected_ingredients:
                for item in POTION_INGREDIENTS:
                    if item['value'] == val: selected_names.append(f"{item['emoji']} {item['label']}")
            embed.add_field(name="⚗️ ส่วนผสมที่เลือก", value="\n".join(selected_names) if selected_names else "ยังไม่เลือก", inline=False)
            embed.add_field(name="💰 ต้นทุนรวม", value=f"**{total_cost:,} {CURRENCY_SYMBOL}**", inline=False)
            self._update_components()
            await interaction.response.edit_message(embed=embed, view=self)

    async def start_brew(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("คุณไม่ใช่เจ้าของหม้อปรุงยานี้", ephemeral=True)
        total_cost = self.get_total_cost()
        conn = self.cog._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM royals WHERE user_id = ?", (interaction.user.id,))
        res = cursor.fetchone()
        balance = res[0] if res else 0
        conn.close()
        
        if balance < total_cost: return await interaction.response.send_message(f"❌ เงินไม่พอ (ต้องการ {total_cost:,} {CURRENCY_SYMBOL})", ephemeral=True)

        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)

        new_bal_after_deduct = self.cog._process_transaction(interaction.user.id, total_cost, "LUCK_BREW_COST", False)
        receipt = discord.Embed(title="🧾 บันทึกกิจกรรม: ปรุงยา", color=discord.Color.red(), timestamp=datetime.datetime.now())
        receipt.add_field(name="รายการ", value="ซื้อวัตถุดิบปรุงยา", inline=False)
        receipt.add_field(name="จำนวนเงิน", value=f"-{total_cost:,} {CURRENCY_SYMBOL}", inline=True)
        receipt.add_field(name="คงเหลือ", value=f"{new_bal_after_deduct:,} {CURRENCY_SYMBOL}", inline=True)
        await self.cog._notify_wallet_thread(interaction.user, receipt)

        msg = await interaction.followup.send(f"🔥 **{interaction.user.display_name}** เริ่มจุดไฟเคี่ยวหม้อปรุงยา... (ลงทุน: `{total_cost} {CURRENCY_SYMBOL}`)\n*(ปุด... ปุด...)*")
        await asyncio.sleep(3)

        # Scale logic
        scale = min(total_cost / 1000, 1.0)
        if total_cost < 100: weights = [15, 50, 25, 9, 1]
        elif total_cost < 300: weights = [10, 30, 40, 18, 2]
        elif total_cost < 600: weights = [8, 15, 35, 35, 7]
        else: weights = [5, 5, 20, 45, 25]

        tiers = ["Fail", "Low", "Medium", "Good", "Excellent"]
        result = random.choices(tiers, weights=weights, k=1)[0]
        
        bonus, reward = 0, 0
        title_res, desc_res, color_res = "", "", discord.Color.default()

        if result == "Fail":
            reward = 0
            title_res, desc_res, color_res = "💥 หม้อระเบิด!", "การทดลองล้มเหลว! ส่วนผสมเสียหายทั้งหมด ไม่ได้เงินคืน...", discord.Color.dark_red()
        elif result == "Low":
            min_p, max_p = 10, 20
            bonus = int(min_p + (max_p - min_p) * scale)
            reward = total_cost + bonus
            title_res, desc_res, color_res = "🧪 น้ำยาคุณภาพต่ำ (Common)", f"ปรุงออกมาได้แค่ระดับพื้นฐาน ขายคืนได้ทุน + กำไร {bonus} R", discord.Color.light_grey()
        elif result == "Medium":
            min_p, max_p = 30, 50
            bonus = int(min_p + (max_p - min_p) * scale)
            reward = total_cost + bonus
            title_res, desc_res, color_res = "⚗️ น้ำยาคุณภาพปานกลาง (Rare)", f"น้ำยาสีสวยงาม ขายได้กำไร {bonus} R!", discord.Color.blue()
        elif result == "Good":
            min_p, max_p = 40, 90
            bonus = int(min_p + (max_p - min_p) * scale)
            reward = total_cost + bonus
            title_res, desc_res, color_res = "✨ น้ำยาคุณภาพดี (Epic)", f"กลิ่นหอมและประกายแวววาว นี่คือน้ำยาชั้นดี! กำไร {bonus} R", discord.Color.gold()
        elif result == "Excellent":
            min_p, max_p = 100, 200
            bonus = int(min_p + (max_p - min_p) * scale)
            reward = total_cost + bonus
            title_res, desc_res, color_res = "👑 น้ำยาคุณภาพยอดเยี่ยม (Legendary)", f"ความสมบูรณ์แบบ! นี่คือน้ำยาที่หาได้ยากยิ่ง! กำไร {bonus} R", discord.Color.purple()

        self.cog._log_activity(interaction.user.id, "brew_potion")
        final_embed = discord.Embed(title=title_res, description=desc_res, color=color_res)
        final_embed.add_field(name="ต้นทุนวัตถุดิบ", value=f"{total_cost:,} {CURRENCY_SYMBOL}", inline=True)
        
        if reward > 0:
            new_bal = self.cog._process_transaction(interaction.user.id, reward, "LUCK_BREW_SOLD", True)
            final_embed.add_field(name="ขายได้ราคา", value=f"+{reward:,} {CURRENCY_SYMBOL}", inline=True)
            final_embed.add_field(name="กำไรสุทธิ", value=f"**+{bonus:,} {CURRENCY_SYMBOL}**", inline=True)
            reward_receipt = discord.Embed(title="💰 รายรับจากการขายน้ำยา", color=discord.Color.green(), timestamp=datetime.datetime.now())
            reward_receipt.add_field(name="ระดับคุณภาพ", value=result, inline=True)
            reward_receipt.add_field(name="ได้รับ", value=f"+{reward:,} {CURRENCY_SYMBOL}", inline=True)
            reward_receipt.add_field(name="คงเหลือ", value=f"{new_bal:,} {CURRENCY_SYMBOL}", inline=True)
            await self.cog._notify_wallet_thread(interaction.user, reward_receipt)
        else:
            final_embed.add_field(name="ผลตอบแทน", value="0 R (สูญเสียทั้งหมด)", inline=False)

        remaining = self.cog._get_remaining_quota(interaction.user.id, "brew_potion")
        final_embed.set_footer(text=f"โควตาปรุงยาคงเหลือ: {remaining}/2")
        await msg.edit(content=None, embed=final_embed)

# --- ☕ Tea Party Views (RP Mode) ---

class TeaPartyTopicModal(discord.ui.Modal, title='กำหนดหัวข้อการโรลเพลย์'):
    def __init__(self, participants, cog, theme, lobby_message, host):
        super().__init__()
        self.participants = participants
        self.cog = cog
        self.theme = theme
        self.lobby_message = lobby_message 
        self.host = host 

        # สร้าง Input 3 หัวข้อ
        self.topic1 = discord.ui.TextInput(label='หัวข้อที่ 1', default='แนะนำตัวและรินน้ำชา', required=True)
        self.topic2 = discord.ui.TextInput(label='หัวข้อที่ 2', default='ลิ้มรสขนมหวาน', required=True)
        self.topic3 = discord.ui.TextInput(label='หัวข้อที่ 3', default='เรื่องราวในโรงเรียน', required=True)
        self.add_item(self.topic1)
        self.add_item(self.topic2)
        self.add_item(self.topic3)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            embed = self.lobby_message.embeds[0]
            embed.description += "\n\n✅ **งานเริ่มแล้ว!** (กรุณาดูข้อความใหม่ด้านล่าง)"
            embed.color = discord.Color.green()
            await self.lobby_message.edit(embed=embed, view=None)
        except Exception as e:
            print(f"Failed to edit lobby: {e}")

        topics = [self.topic1.value, self.topic2.value, self.topic3.value]
        rp_view = TeaPartyRoleplayView(self.participants, interaction.channel, self.cog, self.theme, topics, self.host)
        await rp_view.start_round(interaction.channel)

class TeaPartyLobbyView(discord.ui.View):
    def __init__(self, host, theme, max_p, cog):
        super().__init__(timeout=300)
        self.host = host
        self.theme = theme
        self.max_p = max_p
        self.cog = cog
        self.participants = [host]
        self.message = None

    def update_lobby_embed(self):
        embed = discord.Embed(title=f"☕ Tea Party: {self.theme}", description=f"👥 **สมาชิก:** {len(self.participants)}/{self.max_p}\nสถานะ: รอคนครบ หรือเจ้าภาพเริ่มงาน", color=discord.Color.from_rgb(255, 182, 193))
        names = [f"{i+1}. {p.mention} {'(Host)' if p==self.host else ''}" for i, p in enumerate(self.participants)]
        embed.add_field(name="รายชื่อ", value="\n".join(names), inline=False)
        return embed

    @discord.ui.button(label="🪑 เข้าร่วม", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.participants: return await interaction.response.send_message("คุณอยู่ในปาร์ตี้แล้ว", ephemeral=True)
        if len(self.participants) >= self.max_p: return await interaction.response.send_message("โต๊ะเต็มแล้ว", ephemeral=True)
        self.participants.append(interaction.user)
        await interaction.response.edit_message(embed=self.update_lobby_embed(), view=self)

    @discord.ui.button(label="🚀 เริ่มงาน (ตั้งหัวข้อ)", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host: return await interaction.response.send_message("เฉพาะ Host เท่านั้น", ephemeral=True)
        if len(self.participants) < 2: return await interaction.response.send_message("ต้องการคนอย่างน้อย 2 คน", ephemeral=True)
        await interaction.response.send_modal(TeaPartyTopicModal(self.participants, self.cog, self.theme, self.message, self.host))

    @discord.ui.button(label="❌ ยกเลิกงาน", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host: return await interaction.response.send_message("เฉพาะเจ้าภาพเท่านั้น", ephemeral=True)
        # [UPDATED] ไม่มีการคืนเงินเพราะฟรี แต่คืนโควตา
        self.cog._remove_last_activity_log(self.host.id, "host_teaparty")
        embed = discord.Embed(title="❌ ปาร์ตี้ถูกยกเลิก", description=f"เจ้าภาพยกเลิกงาน\n(คืนโควตาจัดงาน)", color=discord.Color.dark_grey())
        await interaction.response.edit_message(embed=embed, view=None)

class TeaPartyRoleplayView(discord.ui.View):
    def __init__(self, participants, channel, cog, theme, round_topics, host):
        super().__init__(timeout=1200) 
        self.participants = participants
        self.channel = channel 
        self.cog = cog
        self.theme = theme
        self.current_round = 0
        self.round_topics = round_topics 
        self.host = host 
        self.completed_users = set()
        self.phase_start_time = None
        self.current_message = None
        self.processing_users = set() 
        self.transitioning = False    

    async def start_round(self, channel):
        if self.current_message:
            try:
                embed = self.current_message.embeds[0]
                embed.set_footer(text="รอบนี้จบแล้ว")
                await self.current_message.edit(view=None, embed=embed)
            except: pass

        self.current_round += 1
        self.completed_users.clear()
        self.phase_start_time = discord.utils.utcnow()
        
        topic = self.round_topics[self.current_round - 1]
        
        embed = discord.Embed(
            title=f"☕ Tea Party: Round {self.current_round}/3", 
            description=f"### หัวข้อ: {topic}\n\n"
                        f"👉 **กติกา:** ให้ทุกคนพิมพ์ข้อความโรลเพลย์ในช่องแชทนี้\n"
                        f"✅ เมื่อพิมพ์เสร็จแล้ว ให้กดปุ่ม **'ส่งบทบาท'** ด้านล่าง\n"
                        f"⏳ (รอให้ครบทุกคนเพื่อไปต่อ)", 
            color=discord.Color.gold()
        )
        status_text = self._get_status_text()
        embed.add_field(name="สถานะผู้เล่น", value=status_text)
        
        self.current_message = await channel.send(embed=embed, view=self)
        self.transitioning = False

    def _get_status_text(self):
        lines = []
        for p in self.participants:
            status = "✅ เรียบร้อย" if p.id in self.completed_users else "⏳ กำลังพิมพ์..."
            lines.append(f"{p.mention} : {status}")
        return "\n".join(lines)

    async def _verify_rp_message(self, user):
        try:
            history = [message async for message in self.channel.history(limit=50)]
            for msg in history:
                if msg.author.id == user.id and not msg.author.bot:
                    if msg.created_at >= self.phase_start_time:
                        return True
        except Exception as e:
            print(f"Error verifying RP: {e}")
        return False

    @discord.ui.button(label="✅ ส่งบทบาท (พิมพ์ RP ก่อนกด)", style=discord.ButtonStyle.success)
    async def submit_rp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.participants: 
            return await interaction.response.send_message("คุณไม่ได้อยู่ในปาร์ตี้นี้", ephemeral=True)
        
        if interaction.user.id in self.completed_users: 
            return await interaction.response.send_message("คุณส่งบทบาทในรอบนี้ไปแล้ว", ephemeral=True)

        if interaction.user.id in self.processing_users:
            return await interaction.response.send_message("⏳ กำลังตรวจสอบข้อความของคุณ โปรดรอสักครู่...", ephemeral=True)
        
        self.processing_users.add(interaction.user.id)

        try:
            has_rp = await self._verify_rp_message(interaction.user)
            if not has_rp: 
                self.processing_users.remove(interaction.user.id) 
                return await interaction.response.send_message("⚠️ ระบบไม่พบข้อความของคุณ!\nกรุณา **พิมพ์ข้อความโรลเพลย์ในช่องแชท** ให้เรียบร้อยก่อนกดปุ่มนี้", ephemeral=True)
            
            self.completed_users.add(interaction.user.id)
            self.processing_users.remove(interaction.user.id) 
            
            embed = interaction.message.embeds[0]
            embed.clear_fields()
            embed.add_field(name="สถานะผู้เล่น", value=self._get_status_text())
            await interaction.response.edit_message(embed=embed, view=self)

            if len(self.completed_users) == len(self.participants):
                if self.transitioning: return
                self.transitioning = True

                if self.current_round < 3:
                    await asyncio.sleep(1)
                    await self.start_round(self.channel)
                else:
                    await self.finish_party(self.channel)
        except Exception as e:
            print(f"Error in submit_rp: {e}")
            if interaction.user.id in self.processing_users:
                self.processing_users.remove(interaction.user.id)

    async def finish_party(self, channel):
        if self.current_message:
            await self.current_message.edit(view=None)

        embed = discord.Embed(title="🎉 ปาร์ตี้น้ำชาจบลงแล้ว!", color=discord.Color.purple())
        embed.description = f"ขอบคุณทุกคนที่มาร่วมงานเลี้ยงน้ำชาในวันนี้\n🎁 **ได้รับรางวัล:**\n👑 เจ้าภาพ: `{TEA_REWARD_HOST} {CURRENCY_SYMBOL}`\n🍵 ผู้เข้าร่วม: `{TEA_REWARD_GUEST} {CURRENCY_SYMBOL}`"
        
        await channel.send(embed=embed)
        
        for p in self.participants:
            try:
                reward_amount = TEA_REWARD_HOST if p.id == self.host.id else TEA_REWARD_GUEST
                new_bal = self.cog._process_transaction(p.id, reward_amount, "TEA_PARTY_REWARD", True)
                receipt = discord.Embed(title="☕ ใบเสร็จปาร์ตี้น้ำชา", color=discord.Color.from_rgb(255, 182, 193))
                receipt.add_field(name="ธีม", value=self.theme)
                receipt.add_field(name="บทบาท", value="เจ้าภาพ" if p.id == self.host.id else "ผู้เข้าร่วม")
                receipt.add_field(name="รางวัล", value=f"{reward_amount} {CURRENCY_SYMBOL}")
                receipt.add_field(name="คงเหลือ", value=f"{new_bal:,} {CURRENCY_SYMBOL}")
                await self.cog._notify_wallet_thread(p, receipt)
            except: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(SchoolActivities(bot))
