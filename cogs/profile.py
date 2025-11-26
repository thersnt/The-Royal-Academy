import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import typing
import os
import asyncio
from utils import load_data, save_data, PROFILE_FILE 

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

    # --- ✨ Helper Functions (Async) ---
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

    # --- 🖼️ Embed Creator (Sync) ---
    def create_profile_embed(self, member: discord.Member, data: dict, current_balance: int, rp_count: int, affiliation_data: tuple):
        role_name, logo_url, role_color = affiliation_data
        
        embed = discord.Embed(
            title=f"The Royal Academy",
            description=f"**{data['profile_name']}**", 
            color=role_color
        )
        
        if logo_url and logo_url != 'URL_FOR_DEFAULT_LOGO':
            embed.set_thumbnail(url=logo_url) 
        
        if data.get('image_url'):
            embed.set_image(url=data['image_url'])

        embed.add_field(name="ชั้นปี", value=data['grade'] or "ไม่ระบุ", inline=True)
        embed.add_field(name="สังกัด", value=role_name, inline=True)
        embed.add_field(name="เฟซเคลม", value=data['faceclaim'] or "ไม่ระบุ", inline=True)
        
        # Stats
        embed.add_field(name=f"💰 เงินในบัญชี", value=f"`{current_balance:,} {CURRENCY_SYMBOL}`", inline=True)
        embed.add_field(name="🎭 สถิติการโรลเพลย์", value=f"**{rp_count:,}** โพสต์", inline=True)
        
        details = "• เธรดหลักได้ถูกจัดเตรียมไว้เรียบร้อยแล้ว\n• กดลิงก์เพื่อเข้าไปใช้งานได้ทันที\n"
        embed.add_field(name="💼 รายละเอียดเธรดต่าง ๆ", value=details, inline=False)
        
        # Links
        links = []
        guild_id = member.guild.id
        for key, name in [('thread_id', 'Biography'), ('wallet_thread_id', 'Wallet'), ('inventory_thread_id', 'Inventory'), ('trading_thread_id', 'Trading'), ('desk_thread_id', 'Desk')]:
            tid = data.get(key)
            if tid: links.append(f"• **⚜ {name}** (https://discord.com/channels/{guild_id}/{tid})")
            
        link_value = "\n".join(links) if links else "ไม่พบลิงก์เธรดส่วนตัว"
        embed.add_field(name="🔗 ลิงก์ห้องส่วนตัว", value=link_value, inline=False)
        
        joined_at = member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Unknown"
        embed.set_footer(text=f"วันเข้าเรียน: {joined_at}")
        return embed

    # --- Commands ---

    @app_commands.command(name='setup_profile', description='ลงทะเบียนประวัตินักเรียน')
    async def setup_profile_command(self, interaction: discord.Interaction):
        profiles = load_data(PROFILE_FILE)
        user_id_str = str(interaction.user.id)
        if user_id_str in profiles and 'thread_id' in profiles[user_id_str]:
            thread_id = profiles[user_id_str]['thread_id']
            return await interaction.response.send_message(f"❌ คุณมีโปรไฟล์แล้ว! <#{thread_id}>", ephemeral=True)
        await interaction.response.send_modal(ProfileSetupModal(self.db_path))

    @app_commands.command(name="profile", description="แสดงบัตรนักเรียนของคุณ")
    async def profile_command(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=False)
        target = member or interaction.user
        uid_str = str(target.id)
        
        profiles = load_data(PROFILE_FILE)
        if uid_str not in profiles or 'thread_id' not in profiles[uid_str]:
            return await interaction.followup.send(f"❌ {target.display_name} ยังไม่ได้สร้างโปรไฟล์", ephemeral=True)

        data = profiles[uid_str]
        
        # Async Fetch Data
        balance = await self._get_live_royals_balance(target.id)
        rp_stats = await self._get_rp_stats(target.id)
        
        role_name = data['affiliation_role']
        # Find affiliation data safely
        aff_data = None
        for k, v in AFFILIATION_ROLES.items():
            if v[0] == role_name:
                aff_data = v
                break
        if not aff_data: aff_data = (role_name, data['logo_url'], discord.Color.default())

        embed = self.create_profile_embed(target, data, balance, rp_stats, aff_data)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="add_id_card", description="[STAFF] เพิ่มรูปบัตรนักเรียน")
    async def add_id_card(self, interaction: discord.Interaction, member: discord.Member, image_url: str):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)

        profiles = load_data(PROFILE_FILE)
        if str(member.id) not in profiles:
            return await interaction.response.send_message("❌ ยังไม่มีโปรไฟล์", ephemeral=True)

        profiles[str(member.id)]['id_card_url'] = image_url
        await save_data(profiles, PROFILE_FILE)
        await interaction.response.send_message(f"✅ บันทึกรูปบัตรให้ {member.display_name} แล้ว", ephemeral=True)

    @app_commands.command(name="remove_id_card", description="[STAFF] ลบรูปบัตรนักเรียน")
    async def remove_id_card(self, interaction: discord.Interaction, member: discord.Member):
        if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)

        profiles = load_data(PROFILE_FILE)
        if str(member.id) in profiles and 'id_card_url' in profiles[str(member.id)]:
            del profiles[str(member.id)]['id_card_url']
            await save_data(profiles, PROFILE_FILE)
            await interaction.response.send_message(f"🗑️ ลบรูปบัตรของ {member.display_name} แล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ ไม่พบรูปบัตร", ephemeral=True)

    @app_commands.command(name="my_id_card", description="โชว์บัตรนักเรียน (รูปใหญ่)")
    async def my_id_card(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        # Check permissions if viewing others
        if target.id != interaction.user.id:
            if not any(r.name in STAFF_ACCESS_ROLES for r in interaction.user.roles):
                return await interaction.response.send_message("❌ ดูได้เฉพาะบัตรตัวเอง", ephemeral=True)

        profiles = load_data(PROFILE_FILE)
        url = profiles.get(str(target.id), {}).get('id_card_url')
        
        if not url: return await interaction.response.send_message("❌ ยังไม่มีรูปบัตรนักเรียน", ephemeral=True)
        
        embed = discord.Embed(title="🆔 Student ID Card", color=target.color)
        embed.set_image(url=url)
        embed.set_footer(text=f"Card Holder: {target.display_name}", icon_url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="delete_profile", description="[STAFF] ลบโปรไฟล์และข้อมูลทั้งหมด")
    async def delete_profile(self, interaction: discord.Interaction, member: discord.Member):
        if not any(r.name == STAFF_ROLE_NAME for r in interaction.user.roles):
            return await interaction.response.send_message("❌ ไม่มีสิทธิ์", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        uid_str = str(member.id)
        profiles = load_data(PROFILE_FILE)
        
        if uid_str not in profiles:
            return await interaction.followup.send("⚠️ ไม่พบโปรไฟล์", ephemeral=True)

        # Delete Threads
        p = profiles[uid_str]
        threads = [p.get('thread_id'), p.get('wallet_thread_id'), p.get('inventory_thread_id'), p.get('trading_thread_id'), p.get('desk_thread_id')]
        for tid in threads:
            if tid:
                try: await (self.bot.get_channel(tid)).delete()
                except: pass

        # Delete JSON Data
        del profiles[uid_str]
        await save_data(profiles, PROFILE_FILE)
        
        # Delete DB Data (Optional: Call DataCleanup logic here or let it be)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM royals WHERE user_id=?", (member.id,))
            await db.execute("DELETE FROM inventory WHERE user_id=?", (member.id,))
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
            except: pass # Ignore error if bot role is lower

        # 2. Create Threads
        threads = {}
        try:
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
            await db.commit()

        # 4. Save JSON
        profile = {
            'profile_name': self.data['name'],
            'grade': self.data['grade'],
            'faceclaim': self.data['fc'],
            'image_url': self.data['img'],
            'thread_id': threads['main'].id,
            'wallet_thread_id': threads['wallet'].id,
            'inventory_thread_id': threads['inv'].id,
            'trading_thread_id': threads['trade'].id,
            'desk_thread_id': threads['desk'].id,
            'affiliation_role': role_name,
            'logo_url': logo_url
        }
        
        p_data = load_data(PROFILE_FILE)
        p_data[str(member.id)] = profile
        await save_data(p_data, PROFILE_FILE)

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
        
        # 6. Final Response
        await interaction.followup.send(f"✅ เสร็จสิ้น! เชิญที่ {threads['main'].mention}", ephemeral=False)
        
        # Archive
        for t in threads.values():
            try: await t.edit(archived=True)
            except: pass
        
        await interaction.message.edit(view=None)

async def setup(bot):
    await bot.add_cog(Profile(bot))
