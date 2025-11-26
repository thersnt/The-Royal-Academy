import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import typing
import os
import asyncio
from utils import load_data, save_data, PROFILE_FILE, BALANCE_FILE, ensure_balance_exists 

# --- ⚙️ การตั้งค่าระบบโปรไฟล์ ---
DB_NAME = 'school_data.db' 
STAFF_ROLE_NAME = 'Student Council' 
STAFF_ACCESS_ROLES = ["Student Council", "Professor", "Empress of TRA", "Vault Keeper"] 
# --------------------------------------------------------

# --- 🚨 ข้อมูลสังกัดและโลโก้ ---
AFFILIATION_ROLES = {
    "ourea": ("Ourea", "https://iili.io/f3RXGzg.png", discord.Color.green()),
    "gaia": ("Gaia", "https://iili.io/f3RXVLJ.png", discord.Color.gold()),
    "salacia": ("Salacia", "https://iili.io/f3RXMXa.png", discord.Color.blue()),
    "noblia": ("Noblia", "https://iili.io/f3RX0e1.png", discord.Color.red()),
    "ordinaria": ("Ordinaria", "https://iili.io/f3RXh1R.png", discord.Color.teal()),
    "professor": ("Professor", "https://iili.io/f3RXjgp.png", discord.Color.orange()),
    "royal staff": ("Royal Staff", "https://iili.io/f3RXjgp.png", discord.Color.purple()),
}

def connect_db():
    db_path = os.path.join(os.getcwd(), DB_NAME)
    conn = sqlite3.connect(db_path)
    return conn

# ---------------------------------------------------------------------------------
# --- 🖼️ Helper: สร้าง Embed แสดง Profile Card ---
# ---------------------------------------------------------------------------------
def create_profile_embed(member: discord.Member, data: dict, affiliation_data: tuple):
    role_name = affiliation_data[0]
    logo_url = affiliation_data[1]
    role_color = affiliation_data[2]
    
    embed = discord.Embed(
        title=f"The Royal Academy",
        description=f"**{data['profile_name']}**", 
        color=role_color
    )
    
    if logo_url and logo_url != 'URL_FOR_DEFAULT_LOGO':
        embed.set_thumbnail(url=logo_url) 
    
    if data.get('image_url'):
        embed.set_image(url=data['image_url'])

    # ข้อมูลพื้นฐาน (ตัดเงินและ RP Stats ออกตามที่ขอไว้ก่อนหน้า)
    embed.add_field(name="ชั้นปี", value=data['grade'] or "ไม่ระบุ", inline=True)
    embed.add_field(name="สังกัด", value=role_name, inline=True)
    embed.add_field(name="เฟซเคลม", value=data['faceclaim'] or "ไม่ระบุ", inline=True)
    
    details = (
        "• เธรดหลักได้ถูกจัดเตรียมไว้เรียบร้อยแล้ว\n"
        "• กดลิงก์เพื่อเข้าไปใช้งานได้ทันที\n"
    )
    embed.add_field(name="💼 รายละเอียดเธรดต่าง ๆ", value=details, inline=False)
    
    # 🔗 ลิงก์เธรดส่วนตัว
    bio_id = data.get('thread_id')
    wallet_id = data.get('wallet_thread_id')
    inventory_id = data.get('inventory_thread_id')
    trading_id = data.get('trading_thread_id') 
    desk_id = data.get('desk_thread_id')
    guild_id = member.guild.id
    
    links = []
    if bio_id: links.append(f"• **⚜ Biography (ประวัติ)**(https://discord.com/channels/{guild_id}/{bio_id})")
    if wallet_id: links.append(f"• **⚜ Wallet (กระเป๋าเงิน)**(https://discord.com/channels/{guild_id}/{wallet_id})")
    if inventory_id: links.append(f"• **⚜ Inventory (คลังไอเทม)**(https://discord.com/channels/{guild_id}/{inventory_id})")
    if trading_id: links.append(f"• **⚜ Trading (แลกเปลี่ยน)**(https://discord.com/channels/{guild_id}/{trading_id})")
    if desk_id: links.append(f"• **⚜ Desk (โต๊ะเรียน)**(https://discord.com/channels/{guild_id}/{desk_id})")
        
    link_value = "\n".join(links) if links else "ไม่พบลิงก์เธรดส่วนตัว"
    embed.add_field(name="🔗 ลิงก์ห้องส่วนตัว", value=link_value, inline=False)
    
    joined_at = member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Unknown"
    embed.set_footer(text=f"วันเข้าเรียน: {joined_at}")
    
    return embed

# --- Modal/View Logic ---
class ProfileSetupModal(discord.ui.Modal, title='ตั้งค่าโปรไฟล์สมาชิก'):
    def __init__(self, ctx: commands.Context):
        super().__init__()
        self.ctx = ctx
        self.profile_name = discord.ui.TextInput(label='ชื่อตัวละคร', placeholder='กรุณาใส่ชื่อตัวละครที่ต้องการใช้', required=True, max_length=50)
        self.grade_input = discord.ui.TextInput(label='ชั้นปี', placeholder='เช่น Floret, Tiara, Coronet', required=True, max_length=20)
        self.faceclaim_input = discord.ui.TextInput(label='เฟซเคลม', placeholder='ชื่อเฟซเคลม', required=True, max_length=50)
        self.image_url = discord.ui.TextInput(label='ลิงก์รูปภาพตัวละคร', placeholder='URL รูปภาพ (เช่น .png, .jpg)', required=True)
        self.add_item(self.profile_name); self.add_item(self.grade_input); self.add_item(self.faceclaim_input); self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = AffiliationSelectView(self.ctx, self.profile_name.value, self.grade_input.value, self.faceclaim_input.value, self.image_url.value)
        await interaction.followup.send("✅ ข้อมูลเบื้องต้นบันทึกแล้ว! กรุณาเลือกสังกัดของคุณ:", view=view, ephemeral=True)

class AffiliationSelectView(discord.ui.View):
    def __init__(self, ctx: commands.Context, name: str, grade: str, faceclaim: str, image_url: str):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.profile_name = name
        self.grade = grade
        self.faceclaim = faceclaim
        self.image_url = image_url
        self.add_item(self.AffiliationSelect())
        
    class AffiliationSelect(discord.ui.Select):
        def __init__(self):
            options = [discord.SelectOption(label=name, value=key) for key, (name, url, color) in AFFILIATION_ROLES.items()]
            super().__init__(placeholder="เลือกสังกัดของคุณที่นี่", options=options, custom_id="affiliation_selector")

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer() 
            member = interaction.user
            affiliation_key = self.values[0] 
            await self.view.create_full_profile(interaction, member, affiliation_key)
            await interaction.message.edit(view=None) 

    async def create_full_profile(self, interaction: discord.Interaction, member: discord.Member, affiliation_key: str):
        role_name, logo_url, role_color = AFFILIATION_ROLES[affiliation_key]
        conn = connect_db() 
        user_id_str = str(member.id)
        
        role_to_assign = discord.utils.get(member.guild.roles, name=role_name)
        if role_to_assign:
            try: await member.add_roles(role_to_assign)
            except discord.Forbidden: return await interaction.followup.send("❌ บอทไม่มีสิทธิ์มอบยศ!", ephemeral=True)

        main_thread, wallet_thread, inventory_thread, trading_thread, desk_thread = None, None, None, None, None
        try:
            main_thread = await interaction.channel.create_thread(name=f"📜—Biography", type=discord.ChannelType.private_thread, reason=f"Bio for {member.name}")
            await asyncio.sleep(0.5)
            wallet_thread = await interaction.channel.create_thread(name=f"💰—Wallet", type=discord.ChannelType.private_thread, reason=f"Wallet for {member.name}")
            await asyncio.sleep(0.5)
            inventory_thread = await interaction.channel.create_thread(name=f"📦—Inventory", type=discord.ChannelType.private_thread, reason=f"Inventory for {member.name}")
            await asyncio.sleep(0.5)
            trading_thread = await interaction.channel.create_thread(name=f"⚔️—Trading", type=discord.ChannelType.private_thread, reason=f"Trading for {member.name}")
            await asyncio.sleep(0.5)
            desk_thread = await interaction.channel.create_thread(name=f"📚—Desk", type=discord.ChannelType.private_thread, reason=f"Desk for {member.name}")
        except Exception as e:
            return await interaction.followup.send(f"🚨 ข้อผิดพลาดในการสร้างเธรด: {e}", ephemeral=True)
            
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT application_text FROM applications WHERE user_id = ?", (member.id,))
            app_data = cursor.fetchone()
            app_text = app_data[0] if app_data else "ไม่พบประวัติการสมัครเดิมที่รอการอนุมัติ"
            if app_data:
                cursor.execute("DELETE FROM applications WHERE user_id = ?", (member.id,))
                conn.commit()
        finally:
            conn.close()

        profile_data = {
            'profile_name': self.profile_name,
            'grade': self.grade,
            'faceclaim': self.faceclaim, 
            'image_url': self.image_url,
            'thread_id': main_thread.id,             
            'wallet_thread_id': wallet_thread.id,    
            'inventory_thread_id': inventory_thread.id, 
            'trading_thread_id': trading_thread.id,    
            'desk_thread_id': desk_thread.id,
            'affiliation_role': role_name,
            'logo_url': logo_url
        }
        
        profiles = load_data(PROFILE_FILE)
        profiles[user_id_str] = profile_data
        await save_data(profiles, PROFILE_FILE)
        
        staff_mentions = []
        for role_name_config in STAFF_ACCESS_ROLES:
            role_obj = discord.utils.get(interaction.guild.roles, name=role_name_config)
            if role_obj: staff_mentions.append(role_obj.mention)
        staff_tag_string = " ".join(staff_mentions) if staff_mentions else "ทีมงาน"
        
        threads_to_add = [main_thread, wallet_thread, inventory_thread, trading_thread, desk_thread]
        for t in threads_to_add:
            if t:
                await t.add_user(member) 
                await asyncio.sleep(0.2) 

        await main_thread.send(f"{staff_tag_string}\n> **📜 ยินดีต้อนรับสู่ Biography Thread!**\n> \n> **👤 เจ้าของโปรไฟล์:** {member.mention}\n> **📄 ประวัติการสมัคร:**\n> \n{app_text.replace(chr(10), chr(10)+'> ')}")
        await wallet_thread.send(f"{staff_tag_string}\n> **💰 Wallet Thread**\n> 🏦 ใช้สำหรับดูยอดเงินและทำธุรกรรม\n> ❗ใช้คำสั่ง /balance เพื่อดูยอดเงิน")
        await inventory_thread.send(f"{staff_tag_string}\n> **📦 Inventory Thread**\n> 📜 ใช้จัดการไอเทม\n> ❗ใช้คำสั่ง /inventory เพื่อดูทรัพย์สิน")
        await trading_thread.send(f"{staff_tag_string}\n> **⚔️ Trading Thread**\n> 🤝 ใช้แลกเปลี่ยน Royals และไอเทม")
        await desk_thread.send(f"{staff_tag_string}\n> **📚 Desk Thread**\n> 🛎️ ใช้ส่งการบ้านหรือติดต่ออาจารย์")

        embed = create_profile_embed(member, profile_data, (role_name, logo_url, role_color))
        await interaction.followup.send(content=f"✅ สร้างโปรไฟล์สำเร็จ! เข้าห้องส่วนตัวได้ที่ {main_thread.mention}", embed=embed, ephemeral=False)

        for t in threads_to_add:
            if t:
                try: await t.edit(archived=True)
                except: pass

# --- Cog Class และ Command ---
class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='setup_profile', description='ตั้งค่าชื่อ, ชั้นปี, รูปภาพ และเลือกสังกัดของคุณ')
    async def setup_profile_command(self, interaction: discord.Interaction):
        ctx = await commands.Context.from_interaction(interaction)
        profiles = load_data(PROFILE_FILE)
        user_id_str = str(interaction.user.id)
        if user_id_str in profiles and 'thread_id' in profiles[user_id_str]:
            thread_id = profiles[user_id_str]['thread_id']
            return await interaction.response.send_message(f"❌ คุณมีโปรไฟล์แล้ว! <#{thread_id}>", ephemeral=True)
        await interaction.response.send_modal(ProfileSetupModal(ctx))

    @app_commands.command(name="profile", description="แสดงโปรไฟล์และลิงก์ห้องล็อคเกอร์ส่วนตัวของคุณ")
    async def profile_command(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=False)
        target_member = member or interaction.user
        user_id_str = str(target_member.id)
        
        profiles = load_data(PROFILE_FILE)
        if user_id_str not in profiles or 'thread_id' not in profiles[user_id_str]:
            return await interaction.followup.send(f"❌ {target_member.display_name} ยังไม่ได้สร้างโปรไฟล์", ephemeral=True)

        data = profiles[user_id_str]
        role_name = data['affiliation_role']
        logo_url = data['logo_url']
        role_data_tuple = next((v for k, v in AFFILIATION_ROLES.items() if v[0] == role_name), (role_name, logo_url, discord.Color.default()))
        
        embed = create_profile_embed(target_member, data, role_data_tuple)
        await interaction.followup.send(embed=embed)

    # --- ✨ NEW: Add ID Card (Staff Only) ---
    @app_commands.command(name="add_id_card", description="[STAFF] เพิ่มรูปบัตรนักเรียนให้สมาชิก")
    @app_commands.describe(member="สมาชิกเจ้าของบัตร", image_url="ลิงก์รูปภาพบัตรนักเรียน")
    async def add_id_card(self, interaction: discord.Interaction, member: discord.Member, image_url: str):
        # เช็คสิทธิ์ Staff
        user_roles = [r.name for r in interaction.user.roles]
        if not any(r in STAFF_ACCESS_ROLES for r in user_roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        profiles = load_data(PROFILE_FILE)
        user_id_str = str(member.id)

        if user_id_str not in profiles:
            return await interaction.followup.send(f"❌ สมาชิก {member.display_name} ยังไม่ได้ลงทะเบียนโปรไฟล์", ephemeral=True)

        # อัปเดตข้อมูล
        profiles[user_id_str]['id_card_url'] = image_url
        await save_data(profiles, PROFILE_FILE)

        await interaction.followup.send(f"✅ บันทึกรูปบัตรนักเรียนให้ **{member.display_name}** เรียบร้อยแล้ว", ephemeral=True)

    # --- ✨ NEW: Remove ID Card (Staff Only) ---
    @app_commands.command(name="remove_id_card", description="[STAFF] ลบรูปบัตรนักเรียนของสมาชิก")
    @app_commands.describe(member="สมาชิกที่ต้องการลบรูปบัตร")
    async def remove_id_card(self, interaction: discord.Interaction, member: discord.Member):
        # เช็คสิทธิ์ Staff
        user_roles = [r.name for r in interaction.user.roles]
        if not any(r in STAFF_ACCESS_ROLES for r in user_roles):
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        profiles = load_data(PROFILE_FILE)
        user_id_str = str(member.id)

        if user_id_str not in profiles:
            return await interaction.followup.send(f"❌ สมาชิก {member.display_name} ยังไม่ได้ลงทะเบียนโปรไฟล์", ephemeral=True)

        # ลบข้อมูล
        if 'id_card_url' in profiles[user_id_str]:
            del profiles[user_id_str]['id_card_url']
            await save_data(profiles, PROFILE_FILE)
            await interaction.followup.send(f"🗑️ ลบรูปบัตรนักเรียนของ **{member.display_name}** เรียบร้อยแล้ว", ephemeral=True)
        else:
            await interaction.followup.send(f"⚠️ สมาชิกคนนี้ไม่มีรูปบัตรนักเรียนอยู่แล้ว", ephemeral=True)

    # --- ✨ NEW: My ID Card (Showcase Style) ---
    @app_commands.command(name="my_id_card", description="โชว์บัตรนักเรียนของคุณ (Staff ดูของคนอื่นได้)")
    @app_commands.describe(member="สมาชิกที่ต้องการดูบัตร (เฉพาะ Staff)")
    async def my_id_card(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer(ephemeral=False) # แสดงแบบ Public
        
        target = member or interaction.user
        
        # 🔒 Permission Check: ถ้าดูคนอื่น ต้องเป็น Staff
        if member and member.id != interaction.user.id:
            user_roles = [r.name for r in interaction.user.roles]
            if not any(r in STAFF_ACCESS_ROLES for r in user_roles):
                return await interaction.followup.send("❌ คุณสามารถดูได้แค่บัตรของตัวเองเท่านั้นค่ะ", ephemeral=True)

        profiles = load_data(PROFILE_FILE)
        user_id_str = str(target.id)

        if user_id_str not in profiles:
            return await interaction.followup.send(f"❌ {target.display_name} ยังไม่ได้ลงทะเบียนโปรไฟล์", ephemeral=True)

        id_card_url = profiles[user_id_str].get('id_card_url')

        if not id_card_url:
            return await interaction.followup.send(f"❌ {target.display_name} ยังไม่มีรูปบัตรนักเรียน", ephemeral=True)

        # สร้าง Embed สไตล์ Display Item (เน้นรูปใหญ่)
        embed = discord.Embed(
            title="🆔 Student ID Card",
            color=target.color
        )
        embed.set_image(url=id_card_url)
        embed.set_footer(text=f"Card Holder: {target.display_name}", icon_url=target.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="delete_profile", description="[STAFF] ลบโปรไฟล์ทั้งหมดของสมาชิก")
    @app_commands.describe(member="สมาชิกที่คุณต้องการลบโปรไฟล์")
    async def delete_profile_command(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME)
        if staff_role not in interaction.user.roles:
            return await interaction.followup.send(f"❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
            
        member_id_str = str(member.id)
        profiles = load_data(PROFILE_FILE) 
        if member_id_str not in profiles:
              return await interaction.followup.send(f"⚠️ ไม่พบโปรไฟล์ของ {member.display_name}", ephemeral=True)

        p_data = profiles[member_id_str]
        ids_to_delete = [p_data.get('thread_id'), p_data.get('wallet_thread_id'), p_data.get('inventory_thread_id'), p_data.get('trading_thread_id'), p_data.get('desk_thread_id')]
        for t_id in [i for i in ids_to_delete if i]:
            thread = self.bot.get_channel(t_id)
            if thread:
                try: await thread.delete()
                except: pass

        del profiles[member_id_str]
        await save_data(profiles, PROFILE_FILE)
        await interaction.followup.send(f"🗑️ ลบโปรไฟล์ {member.display_name} เรียบร้อยแล้ว", ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))

async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))

