import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import time 
import typing
import os

# --- Config ---
DB_NAME = 'school_data.db'
STAFF_ROLE_NAME = 'Student Council'       
START_ROLE_NAME = 'newbie'              
WELCOME_CHANNEL_ID = 1441105584056303780 
STAFF_ALERT_CHANNEL_ID = 1441128039416201246

# 🚨 [UPDATED] แก้ไขคีย์ royal_staff -> royalstaff เพื่อไม่ให้ชนกับตัวแบ่ง _
AFFILIATION_ROLES = {
    "ourea": "Ourea", 
    "gaia": "Gaia", 
    "salacia": "Salacia", 
    "noblia": "Noblia", 
    "ordinaria": "Ordinaria", 
    "professor": "Professor",
    "royalstaff": "Royal Staff" # ✅ แก้ไขตรงนี้ (ลบ _ ออกจากคีย์)
}

# --- Anti-Spam Cooldowns ---
LAST_JOIN_TIME = 0.0
LAST_JOIN_MEMBER_ID = 0

# --- Database Connection ---
def connect_db():
    db_path = os.path.join(os.getcwd(), DB_NAME)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER PRIMARY KEY,
            application_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_data ( 
            user_id INTEGER PRIMARY KEY, 
            is_approved BOOLEAN DEFAULT 0
        );
    ''')
    conn.commit()
    return conn

# --- View และ Modal Logic ---
class AffiliationView(discord.ui.View):
    def __init__(self, target_user_id: int):
        super().__init__(timeout=None)
        self.target_user_id = target_user_id
        
        # สร้างปุ่มตามรายการใน AFFILIATION_ROLES
        for key, name in AFFILIATION_ROLES.items():
            self.add_item(self.create_button(key, name))
        
        reject_btn = discord.ui.Button(label="❌ ปฏิเสธ (ให้แก้ประวัติ)", style=discord.ButtonStyle.danger, custom_id=f"reject_{self.target_user_id}")
        reject_btn.callback = self.reject_callback
        self.add_item(reject_btn)

    def create_button(self, key, name):
        btn = discord.ui.Button(label=name, style=discord.ButtonStyle.secondary, custom_id=f"affil_{key}_{self.target_user_id}")
        btn.callback = self.approve_callback
        return btn

    def clear_application_db(self, user_id):
        conn = connect_db()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM applications WHERE user_id = ?", (user_id,))
            conn.commit()
        finally:
            conn.close()

    async def approve_callback(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        
        # การแยกข้อมูล (Split) จะทำงานถูกต้องแล้ว เพราะคีย์ไม่มี _
        try:
            _, affiliation_id_key, target_id_str = interaction.data['custom_id'].split('_')
            target_user_id = int(target_id_str)
        except ValueError:
             return await interaction.followup.send("❌ เกิดข้อผิดพลาดในการอ่านข้อมูลปุ่ม (Format Error)", ephemeral=True)

        member = interaction.guild.get_member(target_user_id)
        
        if member is None: return await interaction.followup.send(f"❌ ผู้สมัคร ID `{target_user_id}` ไม่อยู่ในเซิร์ฟเวอร์แล้ว", ephemeral=True)
            
        conn = connect_db() 
        try:
            role_name = AFFILIATION_ROLES[affiliation_id_key]
            role_to_assign = discord.utils.get(interaction.guild.roles, name=role_name)
            newbie_role = discord.utils.get(interaction.guild.roles, name=START_ROLE_NAME)
            
            if role_to_assign is None: return await interaction.followup.send(f"❌ ไม่พบยศชื่อ `{role_name}` ในเซิร์ฟเวอร์!", ephemeral=True)

            await member.add_roles(role_to_assign)
            if newbie_role and newbie_role in member.roles: await member.remove_roles(newbie_role)
            
            conn.execute("UPDATE user_data SET is_approved = 1 WHERE user_id = ?", (target_user_id,))
            conn.execute("DELETE FROM applications WHERE user_id = ?", (target_user_id,)) 
            conn.commit() 
            
            await interaction.message.edit(content=f"✅ อนุมัติโดย: {interaction.user.display_name} | มอบยศ **{role_name}** ให้กับ {member.mention} แล้ว", view=None, embeds=[])
        
        except Exception as e:
            await interaction.followup.send(f"🚨 เกิดข้อผิดพลาดในการมอบยศ: {e}", ephemeral=True)
        finally:
            conn.close() 

    async def reject_callback(self, interaction: discord.Interaction):
        await interaction.response.defer() 
        uid = interaction.data['custom_id'].split('_')[1]
        self.clear_application_db(int(uid))
        member = interaction.guild.get_member(int(uid))
        
        await interaction.message.edit(content=f"🛑 ปฏิเสธสมาชิก {member.mention if member else uid} แล้ว", view=None, embeds=[])
        if member:
            try: await member.send("❌ ประวัติของคุณไม่ผ่านการพิจารณา กรุณาแก้ไขและส่งใหม่ด้วยคำสั่ง `/apply`")
            except: pass

class ApplicationModal(discord.ui.Modal, title='ส่งประวัติการสมัครเข้าสังกัด'):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.application_text = discord.ui.TextInput(label='ประวัติและรายละเอียดของคุณ', style=discord.TextStyle.paragraph, placeholder='กรุณาใส่ประวัติโดยละเอียด (ต้องมากกว่า 50 ตัวอักษร)', required=True, min_length=50, max_length=1500)
        self.add_item(self.application_text)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True) 
        application_text = self.application_text.value
        conn = connect_db()
        
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT application_text FROM applications WHERE user_id = ?", (interaction.user.id,))
            if cursor.fetchone():
                return await interaction.followup.send("❌ คุณได้ส่งใบสมัครไปแล้ว และยังรอการตรวจสอบอยู่...", ephemeral=True)
            
            cursor.execute("INSERT INTO applications (user_id, application_text) VALUES (?, ?)", (interaction.user.id, application_text))
            conn.commit()

            alert_channel = self.bot.get_channel(STAFF_ALERT_CHANNEL_ID)
            staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE_NAME)
            
            if alert_channel and staff_role:
                embed = discord.Embed(title="🚨 ใบสมัครใหม่รอตรวจสอบ!", color=discord.Color.red())
                embed.add_field(name="ผู้สมัคร", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
                embed.add_field(name="ข้อความประวัติ", value=application_text[:1024], inline=False)
                
                await alert_channel.send(content=f"📝 ใบสมัครจาก {interaction.user.mention}", embed=embed, view=AffiliationView(interaction.user.id))
            
            await interaction.followup.send("✅ **ส่งประวัติสำเร็จ!**", ephemeral=True)
        
        finally:
            conn.close()

class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot: return

        global LAST_JOIN_TIME, LAST_JOIN_MEMBER_ID
        current_time = time.time()
        
        if member.id == LAST_JOIN_MEMBER_ID and current_time - LAST_JOIN_TIME < 1.0:
            return
            
        LAST_JOIN_MEMBER_ID = member.id
        LAST_JOIN_TIME = current_time
        
        conn = connect_db()
        cursor = conn.cursor()

        try:
            role = discord.utils.get(member.guild.roles, name=START_ROLE_NAME)
            if role:
                await member.add_roles(role)
        
            welcome_channel = member.guild.get_channel(WELCOME_CHANNEL_ID) 
            if welcome_channel:
                await welcome_channel.send(f'**ยินดีต้อนรับ** {member.mention} สู่โรงเรียนแห่งนี้! ✨\n'
                                             f'กรุณาส่งประวัติของคุณด้วยคำสั่ง `/apply` เพื่อเข้าสังกัดค่ะ')

            cursor.execute("INSERT OR IGNORE INTO user_data (user_id) VALUES (?)", (member.id,))
            conn.commit()
            
        except discord.Forbidden:
            print("PERMISSION ERROR: Bot lacks permissions (Manage Roles or Send Messages).")
        except Exception as e:
            print(f"CRITICAL ERROR in on_member_join: {e}")
        finally:
            conn.close()
    
    @app_commands.command(name='apply')
    async def submit_application_slash(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModal(self.bot))

async def setup(bot):
    await bot.add_cog(Roles(bot))
