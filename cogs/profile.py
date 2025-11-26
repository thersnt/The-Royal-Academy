import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import typing
import os
import asyncio
import datetime

# --- ⚙️ การตั้งค่า ---
CURRENCY_SYMBOL = "R" 
DB_NAME = 'school_data.db' 
STAFF_ROLE_NAME = 'Student Council' 
STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"] 

AFFILIATION_ROLES = {
    "ourea": ("Ourea", "https://iili.io/f3RXGzg.png", discord.Color.green()),
    "gaia": ("Gaia", "https://iili.io/f3RXVLJ.png", discord.Color.gold()),
    "salacia": ("Salacia", "https://iili.io/f3RXMXa.png", discord.Color.blue()),
    "noblia": ("Noblia", "https://iili.io/f3RX0e1.png", discord.Color.red()),
    "ordinaria": ("Ordinaria", "https://iili.io/f3RXh1R.png", discord.Color.teal()),
    "professor": ("Professor", "https://iili.io/f3RXjgp.png", discord.Color.orange()),
    "royal staff": ("Royal Staff", "https://iili.io/f3RXjgp.png", discord.Color.purple()),
}

class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = os.path.join(os.getcwd(), DB_NAME)

    async def cog_load(self):
        # สร้างตาราง student_profiles ในฐานข้อมูล
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS student_profiles (
                    user_id INTEGER PRIMARY KEY,
                    profile_name TEXT,
                    grade TEXT,
                    faceclaim TEXT,
                    image_url TEXT,
                    affiliation_role TEXT,
                    logo_url TEXT,
                    thread_id INTEGER,
                    wallet_thread_id INTEGER,
                    inventory_thread_id INTEGER,
                    trading_thread_id INTEGER,
                    desk_thread_id INTEGER,
                    id_card_url TEXT
                )
            """)
            await db.commit()

    # --- ✨ Helper Functions (Async) ---
    async def _get_profile_data(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row # เพื่อให้เรียกชื่อคอลัมน์ได้
            async with db.execute("SELECT * FROM student_profiles WHERE user_id = ?", (user_id,)) as cursor:
                return await cursor.fetchone()

    async def _get_live_royals_balance(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT balance FROM royals WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def _get_rp_stats(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            # เช็คตารางก่อน
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rp_rewards'") as cursor:
                if not await cursor.fetchone(): return 0
            
            async with db.execute("SELECT COUNT(*) FROM rp_rewards WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    # --- 🖼️ Embed Creator ---
    def create_profile_embed(self, member: discord.Member, data: aiosqlite.Row, affiliation_data: tuple):
        role_name, logo_url, role_color = affiliation_data
        
        embed = discord.Embed(
            title=f"The Royal Academy",
            description=f"**{data['profile_name']}**", 
            color=role_color
        )
        
        if logo_url and logo_url != 'URL_FOR_DEFAULT_LOGO':
            embed.set_thumbnail(url=logo_url) 
        
        if data['image_url']:
            embed.set_image(url=data['image_url'])

        embed.add_field(name="ชั้นปี", value=data['grade'] or "ไม่ระบุ", inline=True)
        embed.add_field(name="สังกัด", value=role_name, inline=True)
        embed.add_field(name="เฟซเคลม", value=data['faceclaim'] or "ไม่ระบุ", inline=True)
        
        details = "• เธรดหลักได้ถูกจัดเตรียมไว้เรียบร้อยแล้ว\n• กดลิงก์เพื่อเข้าไปใช้งานได้ทันที\n"
        embed.add_field(name="💼 รายละเอียดเธรดต่าง ๆ", value=details, inline=False)
        
        # Links
        links = []
        guild_id = member.guild.id
        thread_map = {
            'thread_id': 'Biography',
            'wallet_thread_id': 'Wallet',
            'inventory_thread_id': 'Inventory',
            'trading_thread_id': 'Trading',
            'desk_thread_id': 'Desk'
        }
        
        for col, name in thread_map.items():
            tid = data[col]
            if tid: links.append(f"• **⚜ {name}** (https://discord.com/channels/{guild_id}/{tid})")
            
        link_value = "\n".join(links) if links else "ไม่พบลิงก์เธรดส่วนตัว"
        embed.add_field(name="🔗 ลิงก์ห้องส่วนตัว", value=link_value, inline=False)
        
        joined_at = member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Unknown"
        embed.set_footer(text=f"วันเข้าเรียน: {joined_at}")
        return embed

    # --- Commands ---

    @app_commands.command(name='setup_profile', description='ลงทะเบียนประวัตินักเรียน')
    async def setup_profile_command(self, interaction: discord.Interaction):
        # เช็คก่อนว่ามีโปรไฟล์ไหม
        profile = await self._get_profile_data(interaction.user.id)
        if profile:
             return await interaction.response.send_message(f"❌ คุณมีโปรไฟล์แล้ว! <#{profile['thread_id']}>", ephemeral=True)
        
        await interaction.response.send_modal(ProfileSetupModal(self.db_path))

    @app_commands.command(name="profile", description="แสดงบัตรนักเรียนของคุณ")
    async def profile_command(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=False)
        target = member or interaction.user
        
        data = await self._get_profile_data(target.id)
        
        if not data:
            return await interaction.followup.send(f"❌ {target.display_name} ยังไม่ได้สร้างโปรไฟล์", ephemeral=True)
        
        role_name = data['affiliation_role']
        # Find affiliation data safely
        aff_data = None
        for k, v in AFFILIATION_ROLES.items():
            if v[0] == role_name:
                aff_data = v
                break
        if not aff_data: aff_data = (role_name, data['logo_url'], discord.Color.default())

        embed = self.create_profile_embed(target, data, aff_data)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="add_id_card", description="[STAFF] เพิ่มรูปบัตรนักเรียน")
    async def add_id_card(self, interaction: discord.Interaction, member: discord.Member, image_url: str):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        profile = await self._get_profile_data(member.id)
        if not profile:
            return await interaction.followup.send("❌ สมาชิกยังไม่มีโปรไฟล์", ephemeral=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE student_profiles SET id_card_url = ? WHERE user_id = ?", (image_url, member.id))
            await db.commit()

        await interaction.followup.send(f"✅ บันทึกรูปบัตรให้ {member.display_name} แล้ว", ephemeral=True)

    @app_commands.command(name="remove_id_card", description="[STAFF] ลบรูปบัตรนักเรียน")
    async def remove_id_card(self, interaction: discord.Interaction, member: discord.Member):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE student_profiles SET id_card_url = NULL WHERE user_id = ?", (member.id,))
            await db.commit()

        await interaction.followup.send(f"🗑️ ลบรูปบัตรของ {member.display_name} แล้ว", ephemeral=True)

    @app_commands.command(name="my_id_card", description="โชว์บัตรนักเรียน (รูปใหญ่)")
    async def my_id_card(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=False)
        
        target = member or interaction.user
        # Check permissions if viewing others
        if target.id != interaction.user.id:
            if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
                return await interaction.followup.send("❌ ดูได้เฉพาะบัตรตัวเอง", ephemeral=True)

        data = await self._get_profile_data(target.id)
        if not data: return await interaction.followup.send("❌ ยังไม่ได้ลงทะเบียน", ephemeral=True)

        url = data['id_card_url']
        if not url: return await interaction.followup.send("❌ ยังไม่มีรูปบัตรนักเรียน", ephemeral=True)
        
        embed = discord.Embed(title="🆔 Student ID Card", color=target.color)
        embed.set_image(url=url)
        embed.set_footer(text=f"Card Holder: {target.display_name}", icon_url=target.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="delete_profile", description="[STAFF] ลบโปรไฟล์และข้อมูลทั้งหมด")
    async def delete_profile(self, interaction: discord.Interaction, member: discord.Member):
        if not any(r.name == STAFF_ROLE_NAME for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        profile = await self._get_profile_data(member.id)
        if not profile:
             return await interaction.followup.send("⚠️ ไม่พบโปรไฟล์", ephemeral=True)

        # Delete Threads
        threads = [
            profile['thread_id'], profile['wallet_thread_id'], 
            profile['inventory_thread_id'], profile['trading_thread_id'], 
            profile['desk_thread_id']
        ]
        
        for tid in threads:
            if tid:
                try: await (self.bot.get_channel(tid)).delete()
                except: pass

        # Delete Data from DB
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM student_profiles WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM royals WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM inventory WHERE user_id = ?", (member.id,))
            # Add other deletions if needed
            await db.commit()

        await interaction.followup.send(f"🗑️ ลบโปรไฟล์ {member.display_name} เรียบร้อย", ephemeral=False)

# --- UI Classes ---
class ProfileSetupModal(discord.ui.Modal, title='ตั้งค่าโปรไฟล์สมาชิก'):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.profile_name = discord.ui.TextInput(label='ชื่อตัวละคร', required=True)
        self.grade_input = discord.ui.TextInput(label='ชั้นปี', required=True)
        self.faceclaim_input = discord.ui.TextInput(label='เฟซเคลม', required=True)
        self.image_url = discord.ui.TextInput(label='รูปตัวละคร (URL)', required=True)
        self.add_item(self.profile_name); self.add_item(self.grade_input); self.add_item(self.faceclaim_input); self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = AffiliationSelectView(
            self.profile_name.value, self.grade_input.value, 
            self.faceclaim_input.value, self.image_url.value, self.db_path
        )
        await interaction.followup.send("✅ ข้อมูลเบื้องต้นบันทึกแล้ว! กรุณาเลือกสังกัด:", view=view, ephemeral=True)

class AffiliationSelectView(discord.ui.View):
    def __init__(self, name, grade, fc, img, db_path):
        super().__init__(timeout=300)
        self.data = {'name': name, 'grade': grade, 'fc': fc, 'img': img}
        self.db_path = db_path
        
        options = [discord.SelectOption(label=v[0], value=k) for k, v in AFFILIATION_ROLES.items()]
        self.select = discord.ui.Select(placeholder="เลือกสังกัด...", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction):
        await interaction.response.defer()
        member = interaction.user
        key = self.select.values[0]
        role_name, logo_url, _ = AFFILIATION_ROLES[key]
        
        # 1. Assign Role
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role: 
            try: await member.add_roles(role)
            except: pass 

        # 2. Create Threads
        threads = {}
        try:
            # สร้างเธรดแบบไล่ลำดับ (รอ Discord API นิดนึงกัน Rate Limit)
            threads['main'] = await interaction.channel.create_thread(name=f"📜—Biography", type=discord.ChannelType.private_thread)
            await asyncio.sleep(0.5)
            threads['wallet'] = await interaction.channel.create_thread(name=f"💰—Wallet", type=discord.ChannelType.private_thread)
            await asyncio.sleep(0.5)
            threads['inv'] = await interaction.channel.create_thread(name=f"📦—Inventory", type=discord.ChannelType.private_thread)
            await asyncio.sleep(0.5)
            threads['trade'] = await interaction.channel.create_thread(name=f"⚔️—Trading", type=discord.ChannelType.private_thread)
            await asyncio.sleep(0.5)
            threads['desk'] = await interaction.channel.create_thread(name=f"📚—Desk", type=discord.ChannelType.private_thread)
        except Exception as e:
            return await interaction.followup.send(f"Error creating threads: {e}", ephemeral=True)

        # 3. Clear Application DB
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM applications WHERE user_id=?", (member.id,))
            
            # 4. Save to Database (Not JSON)
            await db.execute("""
                INSERT OR REPLACE INTO student_profiles 
                (user_id, profile_name, grade, faceclaim, image_url, affiliation_role, logo_url, 
                 thread_id, wallet_thread_id, inventory_thread_id, trading_thread_id, desk_thread_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                member.id, self.data['name'], self.data['grade'], self.data['fc'], self.data['img'], 
                role_name, logo_url,
                threads['main'].id, threads['wallet'].id, threads['inv'].id, threads['trade'].id, threads['desk'].id
            ))
            await db.commit()

        # 5. Setup Threads (Add User & Send Msgs)
        staffs = []
        for r_name in STAFF_ACCESS_ROLES:
            r = discord.utils.get(interaction.guild.roles, name=r_name)
            if r: staffs.append(r.mention)
        staff_tag = " ".join(staffs) if staffs else "Staff"

        for t in threads.values():
            await t.add_user(member)
            await asyncio.sleep(0.2)
        
        await threads['main'].send(f"{staff_tag}\n> **Biography**\n> {member.mention}")
        await threads['wallet'].send(f"{staff_tag}\n> **Wallet**\n> Use `/balance`")
        await threads['inv'].send(f"{staff_tag}\n> **Inventory**")
        
        # 6. Final Response
        await interaction.followup.send(f"✅ เสร็จสิ้น! เชิญที่ {threads['main'].mention}", ephemeral=False)
        
        # Archive
        for t in threads.values():
            try: await t.edit(archived=True)
            except: pass
        
        await interaction.message.edit(view=None)

async def setup(bot):
    await bot.add_cog(Profile(bot))
